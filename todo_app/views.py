import secrets
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import (
    AnnouncementForm,
    EmployeeProfileForm,
    EventForm,
    HolidayForm,
    InvitationForm,
    LeaveApprovalForm,
    LeaveRequestForm,
    LeaveTypeForm,
    MembershipForm,
    OffboardMembershipForm,
    OrganizationSetupForm,
    TaskAttachmentForm,
    TaskCommentForm,
    TaskForm,
    TeamForm,
    UserRegistrationForm,
)
from .models import (
    Announcement,
    AuditLog,
    EmailVerificationToken,
    EmployeeProfile,
    Event,
    Holiday,
    Invitation,
    LeaveRequest,
    Membership,
    Notification,
    Organization,
    Task,
    TaskAttachment,
    TaskComment,
    Team,
)
from .services import (
    approve_leave_request,
    can_approve_leave_request,
    can_request_leave,
    create_email_verification_token,
    create_audit_log,
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
    verify_email_token,
    visible_tasks_for_membership,
)
from .utils import current_local_date


class MembershipContextMixin:
    def dispatch(self, request, *args, **kwargs):
        self.membership = None
        if request.user.is_authenticated:
            organization_id = request.session.get('active_organization_id')
            self.membership = get_active_membership(request.user, organization_id)
            if self.membership and request.session.get('active_organization_id') != self.membership.organization_id:
                request.session['active_organization_id'] = self.membership.organization_id
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_membership'] = self.membership
        context['organization_memberships'] = self.request.user.memberships.filter(active=True).select_related('organization') if self.request.user.is_authenticated else []
        context['unread_notifications_count'] = self.membership.notifications.filter(is_read=False).count() if self.membership else 0
        return context


def require_membership(request):
    membership = get_active_membership(request.user, request.session.get('active_organization_id'))
    if not membership:
        return None
    request.session['active_organization_id'] = membership.organization_id
    return membership


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')
    membership = require_membership(request)
    if not membership:
        return redirect('organization-create')

    tasks = visible_tasks_for_membership(membership).distinct()
    today = current_local_date()
    context = {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': membership.notifications.filter(is_read=False).count(),
        'tasks_due_today': tasks.filter(due_date=today).count(),
        'overdue_tasks': tasks.filter(due_date__lt=today).exclude(status='done').count(),
        'recent_tasks': tasks[:5],
        'leave_summary': leave_balance_summary(membership),
        'upcoming_holidays': membership.organization.holidays.filter(date__gte=today)[:5],
        'upcoming_events': membership.organization.events.filter(starts_at__date__gte=today)[:5],
        'latest_announcements': membership.organization.announcements.filter(
            publish_at__lte=timezone.now()
        ).order_by('-publish_at')[:5],
    }
    if membership.is_manager or membership.is_owner:
        team_tasks = membership.organization.tasks.all()
        if membership.is_manager and not membership.is_owner:
            team_tasks = visible_tasks_for_membership(membership).distinct()
        context['manager_counts'] = {
            'todo': team_tasks.filter(status='todo').count(),
            'in_progress': team_tasks.filter(status='in_progress').count(),
            'blocked': team_tasks.filter(status='blocked').count(),
            'done': team_tasks.filter(status='done').count(),
        }
        context['unavailable_members'] = membership.organization.leave_requests.filter(
            status='approved',
            start_date__lte=today,
            end_date__gte=today,
        ).select_related('membership', 'leave_type')[:5]
    if membership.is_hr or membership.is_owner:
        context['hr_counts'] = {
            'active_employees': membership.organization.memberships.filter(active=True).count(),
            'pending_leave_requests': membership.organization.leave_requests.filter(status='pending').count(),
            'upcoming_holidays': membership.organization.holidays.filter(date__gte=today).count(),
            'upcoming_events': membership.organization.events.filter(starts_at__date__gte=today).count(),
        }
    if membership.is_owner:
        org_tasks = membership.organization.tasks.all()
        context['owner_counts'] = {
            'active_teams': membership.organization.teams.count(),
            'blocked_tasks': org_tasks.filter(status='blocked').count(),
            'development_tasks': org_tasks.filter(task_type='development').count(),
            'audit_events': membership.organization.audit_logs.count(),
        }
    return render(request, 'tasks/dashboard.html', context)


@login_required
def switch_organization(request, organization_id):
    membership = get_object_or_404(Membership, user=request.user, organization_id=organization_id, active=True)
    request.session['active_organization_id'] = membership.organization_id
    return redirect('dashboard')


@login_required
def organization_create(request):
    if request.method == 'POST':
        form = OrganizationSetupForm(request.POST)
        if form.is_valid():
            organization, membership = create_organization_for_user(
                request.user,
                form.cleaned_data['name'],
                form.cleaned_data['timezone'],
                form.cleaned_data['work_week'],
                form.cleaned_data['leave_year_start'],
            )
            request.session['active_organization_id'] = organization.id
            messages.success(request, 'Organization created and onboarding defaults applied.')
            return redirect('dashboard')
    else:
        form = OrganizationSetupForm()
    return render(request, 'tasks/organization_form.html', {'form': form})


@login_required
def people_list(request):
    membership = require_membership(request)
    if not membership or not (membership.is_hr or membership.is_owner or membership.is_manager):
        return HttpResponseForbidden()
    members = membership.organization.memberships.select_related('user', 'reporting_manager', 'organization')
    teams = membership.organization.teams.prefetch_related('members', 'manager')
    return render(request, 'tasks/people_list.html', {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': membership.notifications.filter(is_read=False).count(),
        'members': members,
        'teams': teams,
    })


@login_required
def accept_invitation(request, token):
    invitation = get_object_or_404(Invitation, token=token, accepted_at__isnull=True)
    membership = create_membership_from_invitation(invitation, request.user)
    request.session['active_organization_id'] = membership.organization_id
    messages.success(request, f'Joined {membership.organization.name}.')
    return redirect('dashboard')


@login_required
def membership_edit(request, pk):
    membership = require_membership(request)
    if not membership or not (membership.is_hr or membership.is_owner):
        return HttpResponseForbidden()
    target = get_object_or_404(Membership, pk=pk, organization=membership.organization)
    profile, _created = EmployeeProfile.objects.get_or_create(membership=target)
    if request.method == 'POST':
        form = MembershipForm(request.POST, instance=target, membership=membership)
        profile_form = EmployeeProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            if profile_form.is_valid():
                profile_form.save()
                create_audit_log(membership.organization, membership, 'membership_updated', target, f'Updated {target.display_name}.')
                return redirect('people-list')
    else:
        form = MembershipForm(instance=target, membership=membership)
        profile_form = EmployeeProfileForm(instance=profile)
    return render(request, 'tasks/membership_edit.html', {'form': form, 'profile_form': profile_form, 'title': f'Edit {target.display_name}'})


@login_required
def membership_offboard(request, pk):
    membership = require_membership(request)
    if not membership or not (membership.is_hr or membership.is_owner):
        return HttpResponseForbidden()
    target = get_object_or_404(Membership, pk=pk, organization=membership.organization)
    if request.method == 'POST':
        form = OffboardMembershipForm(request.POST, membership=membership, target=target)
        if form.is_valid():
            offboard_membership(
                target,
                membership,
                form.cleaned_data['replacement_membership'],
                form.cleaned_data['replacement_manager'],
                form.cleaned_data['reason'],
            )
            messages.success(request, f'{target.display_name} deactivated.')
            return redirect('people-list')
    else:
        form = OffboardMembershipForm(membership=membership, target=target)
    return render(request, 'tasks/simple_form.html', {'form': form, 'title': f'Offboard {target.display_name}'})


@login_required
def team_create(request):
    membership = require_membership(request)
    if not membership or not membership.is_owner:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = TeamForm(request.POST, membership=membership)
        if form.is_valid():
            team = form.save(commit=False)
            team.organization = membership.organization
            team.save()
            form.save_m2m()
            create_audit_log(membership.organization, membership, 'team_created', team, team.name)
            return redirect('people-list')
    else:
        form = TeamForm(membership=membership)
    return render(request, 'tasks/simple_form.html', {'form': form, 'title': 'Create Team'})


@login_required
def invitation_create(request):
    membership = require_membership(request)
    if not membership or not (membership.is_hr or membership.is_owner):
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = InvitationForm(request.POST, membership=membership)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.organization = membership.organization
            invitation.invited_by = membership
            invitation.token = secrets.token_urlsafe(24)
            invitation.expires_at = timezone.now() + timedelta(days=7)
            invitation.save()
            create_audit_log(membership.organization, membership, 'invitation_created', invitation, invitation.email)
            messages.success(request, f'Invitation created for {invitation.email}.')
            return redirect('people-list')
    else:
        form = InvitationForm(membership=membership)
    return render(request, 'tasks/simple_form.html', {'form': form, 'title': 'Invite Member'})


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            verification = create_email_verification_token(user)
            verify_url = request.build_absolute_uri(reverse('verify-email', args=[verification.token]))
            send_mail(
                'Verify your OfficeDiary account',
                f'Open this link to verify your email: {verify_url}',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )
            auth_login(request, user)
            invitation_token = request.GET.get('invite')
            if invitation_token:
                invitation = Invitation.objects.filter(token=invitation_token, accepted_at__isnull=True).first()
                if invitation:
                    membership = create_membership_from_invitation(invitation, user)
                    request.session['active_organization_id'] = membership.organization_id
                    return redirect('dashboard')
            messages.info(request, 'Verification email sent. Check console/backend output if email is not configured.')
            return redirect('organization-create')
    else:
        form = UserRegistrationForm()
    return render(request, 'tasks/register.html', {'form': form})


def verify_email(request, token):
    user = verify_email_token(token)
    if not user:
        return render(request, 'tasks/verification_result.html', {'success': False})
    return render(request, 'tasks/verification_result.html', {'success': True})


class TaskListView(MembershipContextMixin, ListView):
    model = Task
    template_name = 'tasks/task_list.html'
    paginate_by = 10

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if request.user.is_authenticated and not self.membership:
            return redirect('organization-create')
        return response

    def get_queryset(self):
        queryset = visible_tasks_for_membership(self.membership).distinct().order_by('status', 'due_date', '-updated_at')
        q = self.request.GET.get('q')
        status = self.request.GET.get('status')
        priority = self.request.GET.get('priority')
        task_type = self.request.GET.get('task_type')
        team_id = self.request.GET.get('team')
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(task_key__icontains=q))
        if status:
            queryset = queryset.filter(status=status)
        if priority:
            queryset = queryset.filter(priority=priority)
        if task_type:
            queryset = queryset.filter(task_type=task_type)
        if team_id:
            queryset = queryset.filter(team_id=team_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_tasks = self.get_queryset()
        context['status_choices'] = Task.STATUS_CHOICES
        context['task_type_choices'] = Task.TASK_TYPE_CHOICES
        context['teams'] = self.membership.organization.teams.all()
        context['summary'] = {
            'total': user_tasks.count(),
            'todo': user_tasks.filter(status='todo').count(),
            'in_progress': user_tasks.filter(status='in_progress').count(),
            'blocked': user_tasks.filter(status='blocked').count(),
            'done': user_tasks.filter(status='done').count(),
        }
        return context


class TaskDetailView(MembershipContextMixin, DetailView):
    model = Task
    template_name = 'tasks/task_detail.html'

    def get_queryset(self):
        return visible_tasks_for_membership(self.membership).distinct().prefetch_related('comments__author', 'activities__actor')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = TaskCommentForm(request.POST)
        if form.is_valid():
            TaskComment.objects.create(task=self.object, author=request.user, body=form.cleaned_data['body'])
            record_task_activity(self.object, request.user, self.object.status, self.object.progress_stage, form.cleaned_data['body'])
            create_notification(
                self.object.primary_membership or Membership.objects.filter(
                    organization=self.object.organization, user=self.object.primary_assignee
                ).first(),
                'task',
                f'New comment on {self.object.task_key or self.object.title}',
                form.cleaned_data['body'][:200],
                reverse('task-detail', args=[self.object.pk]),
            )
            return redirect('task-detail', pk=self.object.pk)
        context = self.get_context_data(object=self.object, comment_form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comment_form'] = kwargs.get('comment_form', TaskCommentForm())
        context['attachment_form'] = kwargs.get('attachment_form', TaskAttachmentForm())
        return context


@login_required
def task_attachment_upload(request, pk):
    membership = require_membership(request)
    if not membership:
        return redirect('organization-create')
    task = get_object_or_404(visible_tasks_for_membership(membership).distinct(), pk=pk)
    form = TaskAttachmentForm(request.POST, request.FILES)
    if request.method == 'POST' and form.is_valid():
        uploaded = form.save(commit=False)
        uploaded.task = task
        uploaded.uploaded_by = request.user
        uploaded.original_name = request.FILES['file'].name
        uploaded.save()
        create_audit_log(membership.organization, membership, 'task_attachment_uploaded', task, uploaded.original_name)
    return redirect('task-detail', pk=pk)


class TaskCreateView(MembershipContextMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('task-list')

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if request.user.is_authenticated and not self.membership:
            return redirect('organization-create')
        if request.user.is_authenticated and self.membership and not (self.membership.is_owner or self.membership.is_manager):
            return HttpResponseForbidden()
        return response

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['membership'] = self.membership
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.organization = self.membership.organization
        form.instance.task_key = next_task_key(self.membership.organization)
        form.instance.primary_membership = Membership.objects.filter(
            organization=self.membership.organization,
            user=form.cleaned_data['primary_assignee'],
        ).first()
        if form.instance.status == 'done':
            form.instance.completion_timestamp = timezone.now()
        response = super().form_valid(form)
        collaborator_memberships = Membership.objects.filter(
            organization=self.membership.organization,
            user__in=form.cleaned_data['collaborators'],
        )
        self.object.collaborator_memberships.set(collaborator_memberships)
        comment = form.cleaned_data.get('progress_comment', '')
        record_task_activity(self.object, self.request.user, 'todo', '', comment)
        if comment:
            TaskComment.objects.create(task=self.object, author=self.request.user, body=comment)
        create_audit_log(self.membership.organization, self.membership, 'task_created', self.object, self.object.title)
        if self.object.primary_membership:
            create_notification(
                self.object.primary_membership,
                'task',
                f'Task assigned: {self.object.task_key}',
                self.object.title,
                reverse('task-detail', args=[self.object.pk]),
            )
        return response


class TaskUpdateView(MembershipContextMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_url = reverse_lazy('task-list')

    def get_queryset(self):
        queryset = visible_tasks_for_membership(self.membership).distinct()
        if self.membership.is_owner or self.membership.is_manager:
            return queryset
        return queryset.filter(primary_membership=self.membership)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['membership'] = self.membership
        return kwargs

    def form_valid(self, form):
        previous_status = self.object.status
        previous_stage = self.object.progress_stage
        if form.cleaned_data['status'] == 'blocked':
            form.instance.blocked_from_stage = previous_stage
        elif previous_status == 'blocked' and previous_stage == form.cleaned_data['progress_stage'] == '':
            form.instance.progress_stage = self.object.blocked_from_stage
        if form.cleaned_data['status'] == 'done':
            form.instance.completion_timestamp = timezone.now()
        else:
            form.instance.completion_timestamp = None
        form.instance.primary_membership = Membership.objects.filter(
            organization=self.membership.organization,
            user=form.cleaned_data['primary_assignee'],
        ).first()
        response = super().form_valid(form)
        collaborator_memberships = Membership.objects.filter(
            organization=self.membership.organization,
            user__in=form.cleaned_data['collaborators'],
        )
        self.object.collaborator_memberships.set(collaborator_memberships)
        comment = form.cleaned_data.get('progress_comment', '')
        record_task_activity(self.object, self.request.user, previous_status, previous_stage, comment)
        if comment:
            TaskComment.objects.create(task=self.object, author=self.request.user, body=comment)
        create_audit_log(self.membership.organization, self.membership, 'task_updated', self.object, self.object.title)
        return response


class TaskDeleteView(MembershipContextMixin, DeleteView):
    model = Task
    template_name = 'tasks/task_confirm_delete.html'
    success_url = reverse_lazy('task-list')

    def get_queryset(self):
        queryset = visible_tasks_for_membership(self.membership).distinct()
        if self.membership.is_owner or self.membership.is_manager:
            return queryset
        return queryset.filter(user=self.request.user)


@login_required
def leave_home(request):
    membership = require_membership(request)
    if not membership:
        return redirect('organization-create')
    if not can_request_leave(membership):
        return HttpResponseForbidden()
    form = LeaveRequestForm(request.POST or None, membership=membership)
    if request.method == 'POST' and form.is_valid():
        submit_leave_request(
            membership,
            form.cleaned_data['leave_type'],
            form.cleaned_data['start_date'],
            form.cleaned_data['end_date'],
            form.cleaned_data['reason'],
        )
        return redirect('leave-home')
    return render(request, 'tasks/leave_home.html', {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': membership.notifications.filter(is_read=False).count(),
        'form': form,
        'balances': leave_balance_summary(membership),
        'requests': membership.leave_requests.select_related('leave_type', 'approver'),
    })


@login_required
def leave_admin(request):
    membership = require_membership(request)
    if not membership or not (membership.is_hr or membership.is_owner):
        return HttpResponseForbidden()
    leave_types = membership.organization.leave_types.all()
    leave_type_form = LeaveTypeForm(request.POST or None, prefix='type')
    if request.method == 'POST' and 'create_leave_type' in request.POST and leave_type_form.is_valid():
        leave_type = leave_type_form.save(commit=False)
        leave_type.organization = membership.organization
        leave_type.save()
        return redirect('leave-admin')
    pending_requests = [
        leave_request for leave_request in membership.organization.leave_requests.filter(status='pending').select_related('membership', 'leave_type')
        if can_approve_leave_request(membership, leave_request)
    ]
    return render(request, 'tasks/leave_admin.html', {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': membership.notifications.filter(is_read=False).count(),
        'leave_types': leave_types,
        'leave_type_form': leave_type_form,
        'pending_requests': pending_requests,
        'approval_form': LeaveApprovalForm(),
    })


@login_required
def leave_request_decide(request, pk):
    membership = require_membership(request)
    if not membership or not (membership.is_hr or membership.is_owner):
        return HttpResponseForbidden()
    leave_request = get_object_or_404(LeaveRequest, pk=pk, organization=membership.organization)
    if not can_approve_leave_request(membership, leave_request):
        return HttpResponseForbidden()
    form = LeaveApprovalForm(request.POST)
    if request.method == 'POST' and form.is_valid():
        approve_leave_request(
            leave_request,
            membership,
            approve=form.cleaned_data['decision'] == 'approve',
            note=form.cleaned_data['note'],
        )
    return redirect('leave-admin')


@login_required
def holidays_home(request):
    membership = require_membership(request)
    if not membership:
        return redirect('organization-create')
    form = HolidayForm(request.POST or None)
    if request.method == 'POST':
        if not (membership.is_hr or membership.is_owner):
            return HttpResponseForbidden()
        if form.is_valid():
            holiday = form.save(commit=False)
            holiday.organization = membership.organization
            holiday.save()
            create_audit_log(membership.organization, membership, 'holiday_created', holiday, holiday.name)
            return redirect('holidays-home')
    return render(request, 'tasks/holidays_home.html', {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': membership.notifications.filter(is_read=False).count(),
        'holidays': membership.organization.holidays.all(),
        'form': form,
    })


@login_required
def events_home(request):
    membership = require_membership(request)
    if not membership:
        return redirect('organization-create')
    form = EventForm(request.POST or None, membership=membership)
    if request.method == 'POST':
        if not (membership.is_hr or membership.is_owner):
            return HttpResponseForbidden()
        if form.is_valid():
            event = form.save(commit=False)
            event.organization = membership.organization
            event.created_by = membership
            event.save()
            form.save_m2m()
            publish_event(event)
            return redirect('events-home')
    events = membership.organization.events.all()
    return render(request, 'tasks/events_home.html', {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': membership.notifications.filter(is_read=False).count(),
        'events': events,
        'form': form,
    })


@login_required
def announcements_home(request):
    membership = require_membership(request)
    if not membership:
        return redirect('organization-create')
    form = AnnouncementForm(request.POST or None, membership=membership)
    if request.method == 'POST':
        if not (membership.is_hr or membership.is_owner):
            return HttpResponseForbidden()
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.organization = membership.organization
            announcement.created_by = membership
            announcement.save()
            form.save_m2m()
            publish_announcement(announcement)
            return redirect('announcements-home')
    announcements = membership.organization.announcements.all()
    return render(request, 'tasks/announcements_home.html', {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': membership.notifications.filter(is_read=False).count(),
        'announcements': announcements,
        'form': form,
    })


@login_required
def notifications_home(request):
    membership = require_membership(request)
    if not membership:
        return redirect('organization-create')
    notifications = membership.notifications.all()
    notifications.filter(is_read=False).update(is_read=True, read_at=timezone.now())
    return render(request, 'tasks/notifications.html', {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': 0,
        'notifications': notifications,
    })


@login_required
def audit_home(request):
    membership = require_membership(request)
    if not membership or not membership.is_owner:
        return HttpResponseForbidden()
    return render(request, 'tasks/audit_home.html', {
        'current_membership': membership,
        'organization_memberships': request.user.memberships.filter(active=True).select_related('organization'),
        'unread_notifications_count': membership.notifications.filter(is_read=False).count(),
        'logs': membership.organization.audit_logs.select_related('actor')[:100],
    })


def discord_login(request):
    state = secrets.token_urlsafe(16)
    request.session['discord_oauth_state'] = state
    auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={settings.DISCORD_CLIENT_ID}"
        f"&redirect_uri={settings.DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={settings.DISCORD_SCOPE}"
        f"&state={state}"
    )
    return redirect(auth_url)


@csrf_exempt
def discord_callback(request):
    code = request.GET.get('code')
    state = request.GET.get('state')
    if not code or state != request.session.get('discord_oauth_state'):
        return HttpResponseBadRequest("Invalid state or missing code.")
    token_response = requests.post(
        'https://discord.com/api/oauth2/token',
        data={
            'client_id': settings.DISCORD_CLIENT_ID,
            'client_secret': settings.DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.DISCORD_REDIRECT_URI,
            'scope': settings.DISCORD_SCOPE,
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=20,
    )
    token_data = token_response.json()
    access_token = token_data.get('access_token')
    if not access_token:
        return HttpResponseBadRequest("Failed to obtain access token.")
    user_response = requests.get(
        'https://discord.com/api/users/@me',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=20,
    )
    user_info = user_response.json()
    discord_email = user_info.get('email')
    discord_username = user_info.get('username')
    if not discord_email:
        return HttpResponseBadRequest("Discord account does not have public email.")
    user, _created = User.objects.get_or_create(
        username=discord_email,
        defaults={'email': discord_email, 'first_name': discord_username}
    )
    auth_login(request, user)
    return redirect('dashboard')
