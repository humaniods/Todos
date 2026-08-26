import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.auth import login, logout
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Announcement,
    Event,
    Holiday,
    Invitation,
    LeaveLedgerEntry,
    LeaveRequest,
    LeaveType,
    Membership,
    Notification,
    Organization,
    Task,
    TaskAttachment,
    TaskComment,
    Team,
)
from .serializers import (
    AnnouncementSerializer,
    EventSerializer,
    HolidaySerializer,
    InvitationSerializer,
    LeaveLedgerEntrySerializer,
    LeaveRequestSerializer,
    LeaveTypeSerializer,
    LoginSerializer,
    MembershipSerializer,
    NotificationSerializer,
    OrganizationSerializer,
    SignupSerializer,
    TaskAttachmentSerializer,
    TaskCommentSerializer,
    TaskSerializer,
    TeamSerializer,
)
from .services import (
    approve_leave_request,
    can_approve_leave_request,
    can_request_leave,
    create_membership_from_invitation,
    create_notification,
    create_organization_for_user,
    get_active_membership,
    leave_balance_summary,
    next_task_key,
    offboard_membership,
    publish_announcement,
    publish_event,
    record_task_activity,
    submit_leave_request,
    visible_tasks_for_membership,
)


class OrganizationApiMixin:
    def get_membership(self, request, org_id):
        membership = get_active_membership(request.user, org_id)
        if not membership:
            return None
        return membership

    def forbidden(self):
        return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)


class AuthSignupApi(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response({'user_id': user.id}, status=status.HTTP_201_CREATED)


class AuthLoginApi(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login(request, serializer.validated_data['user'])
        return Response({'detail': 'Logged in'})


class AuthLogoutApi(APIView):
    def post(self, request):
        logout(request)
        return Response({'detail': 'Logged out'})


class OrganizationListCreateApi(APIView):
    def get(self, request):
        memberships = request.user.memberships.filter(active=True).select_related('organization')
        serializer = OrganizationSerializer([m.organization for m in memberships], many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = OrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization, membership = create_organization_for_user(
            request.user,
            serializer.validated_data['name'],
            serializer.validated_data.get('timezone', 'Asia/Kolkata'),
            serializer.validated_data.get('work_week', 'Mon-Fri'),
            serializer.validated_data['leave_year_start'],
        )
        request.session['active_organization_id'] = organization.id
        return Response(OrganizationSerializer(organization).data, status=status.HTTP_201_CREATED)


class OrganizationDetailApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        return Response(OrganizationSerializer(membership.organization).data)

    def patch(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not membership.is_owner:
            return self.forbidden()
        serializer = OrganizationSerializer(membership.organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class InvitationCreateApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_hr or membership.is_owner):
            return self.forbidden()
        serializer = InvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = Invitation.objects.create(
            organization=membership.organization,
            invited_by=membership,
            token=secrets.token_urlsafe(24),
            expires_at=timezone.now() + timedelta(days=7),
            **serializer.validated_data,
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationAcceptApi(APIView):
    def post(self, request, token):
        invitation = get_object_or_404(Invitation, token=token, accepted_at__isnull=True)
        membership = create_membership_from_invitation(invitation, request.user)
        request.session['active_organization_id'] = membership.organization_id
        return Response(MembershipSerializer(membership).data)


class MemberListApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        queryset = membership.organization.memberships.select_related('user')
        return Response(MembershipSerializer(queryset, many=True).data)


class MemberDetailApi(APIView, OrganizationApiMixin):
    def patch(self, request, org_id, member_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_hr or membership.is_owner):
            return self.forbidden()
        target = get_object_or_404(Membership, organization_id=org_id, pk=member_id)
        allowed = ['display_name', 'reporting_manager_id', 'active']
        if membership.is_owner:
            allowed += ['is_manager', 'is_hr', 'is_owner']
        for field in allowed:
            if field in request.data:
                setattr(target, field, request.data[field])
        target.save()
        return Response(MembershipSerializer(target).data)


class MemberDeactivateApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, member_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_hr or membership.is_owner):
            return self.forbidden()
        target = get_object_or_404(Membership, organization_id=org_id, pk=member_id)
        replacement = Membership.objects.filter(pk=request.data.get('replacement_membership')).first() if request.data.get('replacement_membership') else None
        replacement_manager = Membership.objects.filter(pk=request.data.get('replacement_manager')).first() if request.data.get('replacement_manager') else None
        offboard_membership(target, membership, replacement, replacement_manager, request.data.get('reason', ''))
        return Response({'detail': 'Member deactivated'})


class TeamListCreateApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        return Response(TeamSerializer(membership.organization.teams.all(), many=True).data)

    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not membership.is_owner:
            return self.forbidden()
        serializer = TeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = Team.objects.create(
            organization=membership.organization,
            name=serializer.validated_data['name'],
            manager=serializer.validated_data.get('manager'),
        )
        if 'members' in serializer.validated_data:
            team.members.set(serializer.validated_data['members'])
        return Response(TeamSerializer(team).data, status=status.HTTP_201_CREATED)


class TeamDetailApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id, team_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        team = get_object_or_404(Team, pk=team_id, organization_id=org_id)
        return Response(TeamSerializer(team).data)

    def patch(self, request, org_id, team_id):
        membership = self.get_membership(request, org_id)
        if not membership or not membership.is_owner:
            return self.forbidden()
        team = get_object_or_404(Team, pk=team_id, organization_id=org_id)
        serializer = TeamSerializer(team, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if 'members' in serializer.validated_data:
            team.members.set(serializer.validated_data['members'])
        return Response(TeamSerializer(team).data)


class TeamMembersApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, team_id):
        membership = self.get_membership(request, org_id)
        if not membership or not membership.is_owner:
            return self.forbidden()
        team = get_object_or_404(Team, pk=team_id, organization_id=org_id)
        member = get_object_or_404(Membership, pk=request.data.get('member_id'), organization_id=org_id)
        team.members.add(member)
        return Response({'detail': 'Member added'})

    def delete(self, request, org_id, team_id, member_id):
        membership = self.get_membership(request, org_id)
        if not membership or not membership.is_owner:
            return self.forbidden()
        team = get_object_or_404(Team, pk=team_id, organization_id=org_id)
        member = get_object_or_404(Membership, pk=member_id, organization_id=org_id)
        team.members.remove(member)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskListCreateApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        queryset = visible_tasks_for_membership(membership).distinct()
        return Response(TaskSerializer(queryset, many=True).data)

    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_owner or membership.is_manager):
            return self.forbidden()
        serializer = TaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save(
            organization=membership.organization,
            user=request.user,
            task_key=next_task_key(membership.organization),
            primary_membership=Membership.objects.filter(
                organization=membership.organization,
                user=serializer.validated_data['primary_assignee'],
            ).first(),
        )
        task.collaborator_memberships.set(
            Membership.objects.filter(organization=membership.organization, user__in=task.collaborators.all())
        )
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


class TaskDetailApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        return Response(TaskSerializer(task).data)

    def patch(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        previous_status = task.status
        previous_stage = task.progress_stage
        serializer = TaskSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        record_task_activity(task, request.user, previous_status, previous_stage, request.data.get('comment', ''))
        return Response(TaskSerializer(task).data)


class TaskCommentsApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        comment = TaskComment.objects.create(task=task, author=request.user, body=request.data.get('body', ''))
        return Response(TaskCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class TaskUpdatesApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        previous_status = task.status
        previous_stage = task.progress_stage
        for field in ['status', 'progress_stage', 'blocked_type', 'blocked_reason', 'expected_next_update']:
            if field in request.data:
                setattr(task, field, request.data[field])
        task.save()
        record_task_activity(task, request.user, previous_status, previous_stage, request.data.get('comment', ''))
        return Response(TaskSerializer(task).data)


class TaskBlockApi(TaskUpdatesApi):
    def post(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        previous_status = task.status
        previous_stage = task.progress_stage
        task.status = 'blocked'
        task.blocked_type = request.data.get('blocked_type', task.blocked_type)
        task.blocked_reason = request.data.get('blocked_reason', task.blocked_reason)
        task.blocked_from_stage = previous_stage
        task.save()
        record_task_activity(task, request.user, previous_status, previous_stage, request.data.get('comment', ''))
        return Response(TaskSerializer(task).data)


class TaskUnblockApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        previous_status = task.status
        previous_stage = task.progress_stage
        task.status = 'in_progress'
        if task.blocked_from_stage:
            task.progress_stage = task.blocked_from_stage
        task.blocked_type = ''
        task.blocked_reason = ''
        task.save()
        record_task_activity(task, request.user, previous_status, previous_stage, request.data.get('comment', ''))
        return Response(TaskSerializer(task).data)


class TaskCompleteApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        previous_status = task.status
        previous_stage = task.progress_stage
        task.status = 'done'
        task.completion_timestamp = timezone.now()
        task.save()
        record_task_activity(task, request.user, previous_status, previous_stage, request.data.get('comment', ''))
        return Response(TaskSerializer(task).data)


class TaskReopenApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        previous_status = task.status
        previous_stage = task.progress_stage
        task.status = 'in_progress'
        task.reopened_reason = request.data.get('reason', '')
        if task.task_type == 'development' and not request.data.get('progress_stage'):
            task.progress_stage = 'development'
        elif request.data.get('progress_stage'):
            task.progress_stage = request.data['progress_stage']
        task.completion_timestamp = None
        task.save()
        record_task_activity(task, request.user, previous_status, previous_stage, task.reopened_reason)
        return Response(TaskSerializer(task).data)


class TaskCollaboratorsApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        collaborators = User.objects.filter(id__in=request.data.get('collaborator_ids', []))
        task.collaborators.set(collaborators)
        task.collaborator_memberships.set(Membership.objects.filter(organization_id=org_id, user__in=collaborators))
        return Response(TaskSerializer(task).data)


class TaskAttachmentApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id, task_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=task_id)
        uploaded = request.FILES['file']
        attachment = TaskAttachment.objects.create(task=task, uploaded_by=request.user, file=uploaded, original_name=uploaded.name)
        return Response(TaskAttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


class LeaveTypeListCreateApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        return Response(LeaveTypeSerializer(membership.organization.leave_types.all(), many=True).data)

    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_hr or membership.is_owner):
            return self.forbidden()
        serializer = LeaveTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        leave_type = serializer.save(organization=membership.organization)
        return Response(LeaveTypeSerializer(leave_type).data, status=status.HTTP_201_CREATED)


class LeaveBalanceMeApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not can_request_leave(membership):
            return self.forbidden()
        return Response(leave_balance_summary(membership))


class LeaveRequestListCreateApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        queryset = membership.organization.leave_requests.all() if (membership.is_hr or membership.is_owner) else membership.leave_requests.all()
        return Response(LeaveRequestSerializer(queryset, many=True).data)

    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not can_request_leave(membership):
            return self.forbidden()
        serializer = LeaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        leave_request = submit_leave_request(
            membership,
            serializer.validated_data['leave_type'],
            serializer.validated_data['start_date'],
            serializer.validated_data['end_date'],
            serializer.validated_data.get('reason', ''),
        )
        return Response(LeaveRequestSerializer(leave_request).data, status=status.HTTP_201_CREATED)


class LeaveApproveRejectCancelApi(APIView, OrganizationApiMixin):
    action = 'approve'

    def post(self, request, org_id, request_id):
        membership = self.get_membership(request, org_id)
        leave_request = get_object_or_404(LeaveRequest, pk=request_id, organization_id=org_id)
        if self.action == 'cancel':
            if leave_request.membership != membership and not (membership and (membership.is_hr or membership.is_owner)):
                return self.forbidden()
            leave_request.status = 'cancelled'
            leave_request.save(update_fields=['status', 'updated_at'])
            return Response(LeaveRequestSerializer(leave_request).data)
        if not membership or not can_approve_leave_request(membership, leave_request):
            return self.forbidden()
        leave_request = approve_leave_request(leave_request, membership, approve=self.action == 'approve', note=request.data.get('note', ''))
        return Response(LeaveRequestSerializer(leave_request).data)


class LeaveLedgerAdjustmentApi(APIView, OrganizationApiMixin):
    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_hr or membership.is_owner):
            return self.forbidden()
        target = get_object_or_404(Membership, pk=request.data['membership_id'], organization_id=org_id)
        leave_type = get_object_or_404(LeaveType, pk=request.data['leave_type_id'], organization_id=org_id)
        entry = LeaveLedgerEntry.objects.create(
            organization=membership.organization,
            membership=target,
            leave_type=leave_type,
            entry_type='hr_correction',
            days=request.data['days'],
            note=request.data.get('note', ''),
            created_by=membership,
        )
        return Response(LeaveLedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class HolidayListCreateApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        return Response(HolidaySerializer(membership.organization.holidays.all(), many=True).data)

    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_hr or membership.is_owner):
            return self.forbidden()
        serializer = HolidaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        holiday = serializer.save(organization=membership.organization)
        return Response(HolidaySerializer(holiday).data, status=status.HTTP_201_CREATED)


class EventListCreateApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        return Response(EventSerializer(membership.organization.events.all(), many=True).data)

    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_hr or membership.is_owner):
            return self.forbidden()
        serializer = EventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save(organization=membership.organization, created_by=membership)
        publish_event(event)
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)


class AnnouncementListCreateApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        return Response(AnnouncementSerializer(membership.organization.announcements.all(), many=True).data)

    def post(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership or not (membership.is_hr or membership.is_owner):
            return self.forbidden()
        serializer = AnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(organization=membership.organization, created_by=membership)
        publish_announcement(announcement)
        return Response(AnnouncementSerializer(announcement).data, status=status.HTTP_201_CREATED)


class DashboardApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        tasks = visible_tasks_for_membership(membership)
        return Response({
            'organization': OrganizationSerializer(membership.organization).data,
            'task_counts': {
                'todo': tasks.filter(status='todo').count(),
                'in_progress': tasks.filter(status='in_progress').count(),
                'blocked': tasks.filter(status='blocked').count(),
                'done': tasks.filter(status='done').count(),
            },
            'development_by_checkpoint': list(
                membership.organization.tasks.filter(task_type='development')
                .values('progress_stage').annotate(total=Count('id')).order_by('progress_stage')
            ),
        })


class TeamDashboardApi(APIView, OrganizationApiMixin):
    def get(self, request, org_id, team_id):
        membership = self.get_membership(request, org_id)
        if not membership:
            return self.forbidden()
        team = get_object_or_404(Team, pk=team_id, organization_id=org_id)
        tasks = membership.organization.tasks.filter(team=team)
        return Response({
            'team': TeamSerializer(team).data,
            'task_counts': {
                'todo': tasks.filter(status='todo').count(),
                'in_progress': tasks.filter(status='in_progress').count(),
                'blocked': tasks.filter(status='blocked').count(),
                'done': tasks.filter(status='done').count(),
            },
        })


class NotificationsListApi(APIView):
    def get(self, request):
        membership = get_active_membership(request.user, request.session.get('active_organization_id'))
        if not membership:
            return Response([])
        return Response(NotificationSerializer(membership.notifications.all(), many=True).data)


class NotificationReadApi(APIView):
    def post(self, request, notification_id):
        membership = get_active_membership(request.user, request.session.get('active_organization_id'))
        notification = get_object_or_404(Notification, pk=notification_id, membership=membership)
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])
        return Response({'detail': 'Marked read'})


class NotificationReadAllApi(APIView):
    def post(self, request):
        membership = get_active_membership(request.user, request.session.get('active_organization_id'))
        if not membership:
            return Response({'detail': 'No active organization'}, status=status.HTTP_400_BAD_REQUEST)
        membership.notifications.filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({'detail': 'Marked all read'})
