import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, Sum
from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import (
    Announcement,
    AuditLog,
    EmailVerificationToken,
    EmployeeProfile,
    Invitation,
    LeaveLedgerEntry,
    LeaveRequest,
    LeaveType,
    Membership,
    Notification,
    Organization,
    Task,
    TaskActivity,
    TaskAttachment,
    TaskComment,
    Team,
)


def get_active_membership(user, organization_id=None):
    memberships = user.memberships.filter(active=True).select_related('organization')
    if organization_id:
        return memberships.filter(organization_id=organization_id).first()
    return memberships.order_by('organization__name').first()


def create_notification(membership, category, title, body='', url=''):
    if membership is None:
        return None
    return Notification.objects.create(
        membership=membership,
        category=category,
        title=title,
        body=body,
        url=url,
    )


def create_audit_log(organization, actor, action, target, description=''):
    return AuditLog.objects.create(
        organization=organization,
        actor=actor,
        action=action,
        target_type=target.__class__.__name__ if target else '',
        target_id=getattr(target, 'pk', None),
        description=description,
    )


def create_email_verification_token(user):
    return EmailVerificationToken.objects.create(
        user=user,
        token=secrets.token_urlsafe(24),
        expires_at=timezone.now() + timedelta(days=2),
    )


def verify_email_token(token):
    verification = EmailVerificationToken.objects.filter(
        token=token,
        used_at__isnull=True,
        expires_at__gte=timezone.now(),
    ).select_related('user').first()
    if not verification:
        return None
    verification.user.is_active = True
    verification.user.save(update_fields=['is_active'])
    verification.used_at = timezone.now()
    verification.save(update_fields=['used_at'])
    return verification.user


def next_task_key(organization):
    count = organization.tasks.count() + 1
    prefix = ''.join(part[0] for part in organization.name.split()[:3]).upper() or 'ORG'
    return f'{prefix}-{count:04d}'


def record_task_activity(task, actor, previous_status, previous_stage, comment=''):
    if previous_status == task.status and previous_stage == task.progress_stage and not comment:
        return
    TaskActivity.objects.create(
        task=task,
        actor=actor.user if isinstance(actor, Membership) else actor,
        from_status=previous_status,
        to_status=task.status,
        from_progress_stage=previous_stage,
        to_progress_stage=task.progress_stage,
        comment=comment,
    )


@transaction.atomic
def create_organization_for_user(user, name, timezone_name, work_week, leave_year_start):
    organization = Organization.objects.create(
        name=name,
        timezone=timezone_name,
        work_week=work_week,
        leave_year_start=leave_year_start,
        created_by=user,
    )
    membership = Membership.objects.create(
        organization=organization,
        user=user,
        display_name=user.get_full_name() or user.username,
        is_employee=True,
        is_manager=True,
        is_hr=True,
        is_owner=True,
    )
    EmployeeProfile.objects.create(membership=membership)
    default_team = Team.objects.create(organization=organization, name='General', manager=membership)
    default_team.members.add(membership)
    for leave_name, allocation, carry_forward, reason_required in [
        ('Casual leave', Decimal('12.0'), False, False),
        ('Sick leave', Decimal('10.0'), False, False),
        ('Earned/annual leave', Decimal('18.0'), True, False),
        ('Unpaid leave', Decimal('0.0'), False, True),
    ]:
        leave_type = LeaveType.objects.create(
            organization=organization,
            name=leave_name,
            annual_allocation=allocation,
            allow_carry_forward=carry_forward,
            reason_required=reason_required,
        )
        if allocation:
            LeaveLedgerEntry.objects.create(
                organization=organization,
                membership=membership,
                leave_type=leave_type,
                entry_type='allocation',
                days=allocation,
                note='Initial allocation',
                created_by=membership,
            )
    create_audit_log(organization, membership, 'organization_created', organization, 'Initial organization onboarding completed.')
    return organization, membership


@transaction.atomic
def create_membership_from_invitation(invitation, user):
    membership, created = Membership.objects.get_or_create(
        organization=invitation.organization,
        user=user,
        defaults={
            'display_name': invitation.invited_name or user.get_full_name() or user.username,
            'is_employee': True,
            'is_manager': invitation.role == 'manager',
            'is_hr': invitation.role == 'hr',
            'is_owner': invitation.role == 'owner',
            'reporting_manager': invitation.reporting_manager,
        }
    )
    if invitation.team:
        invitation.team.members.add(membership)
    EmployeeProfile.objects.get_or_create(membership=membership)
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=['accepted_at'])
    create_notification(
        membership,
        'invitation',
        f'Joined {invitation.organization.name}',
        'Your organization membership is now active.',
        '/',
    )
    create_audit_log(invitation.organization, invitation.invited_by, 'invitation_accepted', membership, f'{membership.display_name} joined via invitation.')
    return membership


def visible_tasks_for_membership(membership):
    queryset = Task.objects.filter(organization=membership.organization).select_related(
        'organization', 'team', 'primary_assignee', 'primary_membership', 'user'
    )
    if membership.is_owner:
        return queryset
    if membership.is_manager:
        team_ids = membership.managed_teams.values_list('id', flat=True)
        return queryset.filter(
            Q(team_id__in=team_ids)
            | Q(primary_membership=membership)
            | Q(primary_membership__reporting_manager=membership)
            | Q(primary_assignee=membership.user)
        ).distinct()
    return queryset.filter(
        Q(primary_membership=membership)
        | Q(primary_assignee=membership.user)
    ).distinct()


def leave_balance_summary(membership):
    summaries = []
    for leave_type in membership.organization.leave_types.all():
        ledger_total = leave_type.ledger_entries.filter(membership=membership).aggregate(total=Sum('days'))['total'] or Decimal('0.0')
        pending_days = (
            leave_type.leave_requests.filter(membership=membership, status='pending')
            .count()
        )
        used = abs(leave_type.ledger_entries.filter(
            membership=membership,
            entry_type='approved_leave'
        ).aggregate(total=Sum('days'))['total'] or Decimal('0.0'))
        summaries.append({
            'leave_type': leave_type,
            'allocated': leave_type.annual_allocation,
            'available': ledger_total,
            'used': used,
            'pending': pending_days,
        })
    return summaries


def can_request_leave(membership):
    return bool(membership and not membership.is_owner)


def leave_approvers_for_membership(membership):
    if not membership:
        return Membership.objects.none()
    members = membership.organization.memberships.filter(active=True)
    if membership.is_owner:
        return members.none()
    if membership.is_hr:
        return members.filter(is_owner=True)
    return members.filter(is_hr=True, is_owner=False)


def can_approve_leave_request(approver, leave_request):
    if not approver or approver.organization_id != leave_request.organization_id:
        return False
    requester = leave_request.membership
    if requester.is_owner:
        return False
    if approver.is_owner:
        return requester.is_hr
    if approver.is_hr:
        return not requester.is_hr and not requester.is_owner
    return False


@transaction.atomic
def submit_leave_request(membership, leave_type, start_date, end_date, reason=''):
    if not can_request_leave(membership):
        raise ValueError('Owners cannot request leave.')
    leave_request = LeaveRequest.objects.create(
        organization=membership.organization,
        membership=membership,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )
    for approver in leave_approvers_for_membership(membership):
        create_notification(
            approver,
            'leave',
            f'Leave request from {membership.display_name}',
            f'{leave_type.name}: {start_date} to {end_date}',
            '/leave/admin/',
        )
    create_audit_log(membership.organization, membership, 'leave_requested', leave_request, reason)
    return leave_request


@transaction.atomic
def approve_leave_request(leave_request, approver, approve=True, note=''):
    if not can_approve_leave_request(approver, leave_request):
        raise ValueError('This approver is not allowed to decide the leave request.')
    leave_request.status = 'approved' if approve else 'rejected'
    leave_request.approver = approver
    leave_request.approver_note = note
    leave_request.save(update_fields=['status', 'approver', 'approver_note', 'updated_at'])
    if approve:
        days = Decimal(str((leave_request.end_date - leave_request.start_date).days + 1)) * Decimal('-1.0')
        LeaveLedgerEntry.objects.create(
            organization=leave_request.organization,
            membership=leave_request.membership,
            leave_type=leave_request.leave_type,
            leave_request=leave_request,
            entry_type='approved_leave',
            days=days,
            note=note,
            created_by=approver,
        )
    create_notification(
        leave_request.membership,
        'leave',
        f'Leave request {leave_request.get_status_display()}',
        note or f'{leave_request.leave_type.name}: {leave_request.start_date} to {leave_request.end_date}',
        '/leave/',
    )
    create_audit_log(leave_request.organization, approver, f'leave_{leave_request.status}', leave_request, note)
    return leave_request


@transaction.atomic
def offboard_membership(membership, actor, replacement_membership=None, replacement_manager=None, reason=''):
    if membership.is_owner and membership.organization.memberships.filter(active=True, is_owner=True).exclude(pk=membership.pk).count() == 0:
        raise ValueError('Cannot deactivate the final active owner.')
    open_tasks = membership.organization.tasks.filter(primary_membership=membership).exclude(status='done')
    if open_tasks.exists() and replacement_membership is None:
        raise ValueError('Replacement membership is required to transfer open tasks.')
    if replacement_membership:
        for task in open_tasks:
            previous_status = task.status
            previous_stage = task.progress_stage
            task.primary_membership = replacement_membership
            task.primary_assignee = replacement_membership.user
            task.save(update_fields=['primary_membership', 'primary_assignee', 'updated_at'])
            record_task_activity(task, actor, previous_status, previous_stage, f'Task transferred from {membership.display_name}.')
    if replacement_manager:
        membership.organization.memberships.filter(reporting_manager=membership).update(reporting_manager=replacement_manager)
    membership.active = False
    membership.deactivated_at = timezone.now()
    membership.save(update_fields=['active', 'deactivated_at'])
    _revoke_user_sessions(membership.user)
    create_audit_log(membership.organization, actor, 'membership_offboarded', membership, reason or membership.display_name)
    return membership


def _revoke_user_sessions(user):
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.pk):
            session.delete()


def publish_announcement(announcement):
    recipients = announcement.organization.memberships.filter(active=True)
    if announcement.audience == 'teams':
        recipients = recipients.filter(teams__in=announcement.teams.all()).distinct()
    for membership in recipients:
        create_notification(
            membership,
            'announcement',
            announcement.title,
            announcement.content[:200],
            '/announcements/',
        )
    create_audit_log(announcement.organization, announcement.created_by, 'announcement_published', announcement, announcement.title)


def publish_event(event):
    recipients = event.organization.memberships.filter(active=True)
    if event.audience == 'teams':
        recipients = recipients.filter(teams__in=event.teams.all()).distinct()
    for membership in recipients:
        create_notification(
            membership,
            'event',
            event.title,
            event.description[:200],
            '/events/',
        )
    create_audit_log(event.organization, event.created_by, 'event_published', event, event.title)
