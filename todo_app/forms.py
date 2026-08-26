from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Announcement,
    EmployeeProfile,
    Event,
    Holiday,
    Invitation,
    LeaveRequest,
    LeaveType,
    Membership,
    Organization,
    Task,
    TaskAttachment,
    TaskComment,
    Team,
)
from .utils import current_local_date


class StyledModelForm(forms.ModelForm):
    def _apply_bootstrap(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
            elif isinstance(widget, (forms.SelectMultiple, forms.Select)):
                widget.attrs['class'] = 'form-select'
            else:
                existing = widget.attrs.get('class', '')
                widget.attrs['class'] = f'{existing} form-control'.strip()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class OrganizationSetupForm(StyledModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'timezone', 'work_week', 'leave_year_start']
        widgets = {
            'leave_year_start': forms.DateInput(attrs={'type': 'date'}),
        }


class TeamForm(StyledModelForm):
    class Meta:
        model = Team
        fields = ['name', 'manager', 'members']

    def __init__(self, *args, **kwargs):
        membership = kwargs.pop('membership')
        super().__init__(*args, **kwargs)
        queryset = membership.organization.memberships.filter(active=True)
        self.fields['manager'].queryset = queryset
        self.fields['members'].queryset = queryset


class InvitationForm(StyledModelForm):
    class Meta:
        model = Invitation
        fields = ['email', 'invited_name', 'role', 'team', 'reporting_manager']

    def __init__(self, *args, **kwargs):
        membership = kwargs.pop('membership')
        super().__init__(*args, **kwargs)
        self.membership = membership
        self.fields['team'].queryset = membership.organization.teams.all()
        self.fields['reporting_manager'].queryset = membership.organization.memberships.filter(active=True)
        if not membership.is_owner:
            self.fields['role'].choices = [('employee', 'Employee')]


class MembershipForm(StyledModelForm):
    class Meta:
        model = Membership
        fields = ['display_name', 'is_manager', 'is_hr', 'is_owner', 'reporting_manager', 'active']

    def __init__(self, *args, **kwargs):
        membership = kwargs.pop('membership')
        super().__init__(*args, **kwargs)
        self.fields['reporting_manager'].queryset = membership.organization.memberships.filter(active=True)
        if not membership.is_owner:
            self.fields.pop('is_owner')
            self.fields.pop('is_hr')
            self.fields.pop('is_manager')


class EmployeeProfileForm(StyledModelForm):
    class Meta:
        model = EmployeeProfile
        fields = ['employee_code', 'designation', 'department', 'joining_date']
        widgets = {
            'joining_date': forms.DateInput(attrs={'type': 'date'}),
        }


class TaskForm(StyledModelForm):
    progress_comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Required for blockers, checkpoint changes, and reopen actions.',
    )

    class Meta:
        model = Task
        fields = [
            'team',
            'title',
            'description',
            'due_date',
            'start_date',
            'expected_next_update',
            'priority',
            'task_type',
            'primary_assignee',
            'collaborators',
            'status',
            'progress_stage',
            'blocked_type',
            'blocked_reason',
            'reopened_reason',
            'tags',
        ]
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'expected_next_update': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        membership = kwargs.pop('membership', None)
        super().__init__(*args, **kwargs)
        self.membership = membership
        if membership:
            org_memberships = membership.organization.memberships.filter(active=True).select_related('user')
            team_queryset = membership.organization.teams.all()
            self.fields['team'].queryset = team_queryset
            self.fields['primary_assignee'].queryset = User.objects.filter(memberships__in=org_memberships).distinct().order_by('username')
            self.fields['collaborators'].queryset = self.fields['primary_assignee'].queryset
        else:
            self.fields['team'].queryset = Team.objects.none()
            self.fields['primary_assignee'].queryset = User.objects.order_by('username')
            self.fields['collaborators'].queryset = User.objects.order_by('username')
        if membership and not membership.is_owner and not membership.is_manager:
            self.fields['team'].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        task_type = cleaned_data.get('task_type')
        status = cleaned_data.get('status')
        progress_stage = cleaned_data.get('progress_stage')
        blocked_type = cleaned_data.get('blocked_type')
        blocked_reason = cleaned_data.get('blocked_reason')
        reopened_reason = cleaned_data.get('reopened_reason')
        progress_comment = cleaned_data.get('progress_comment')
        primary_assignee = cleaned_data.get('primary_assignee')

        previous_status = self.instance.status if self.instance.pk else 'todo'
        previous_stage = self.instance.progress_stage if self.instance.pk else ''

        if self.membership and primary_assignee and not Membership.objects.filter(
            organization=self.membership.organization, user=primary_assignee, active=True
        ).exists():
            self.add_error('primary_assignee', 'Assignee must be a member of this organization.')

        if task_type == 'general':
            cleaned_data['progress_stage'] = ''
            cleaned_data['blocked_type'] = ''
            progress_stage = ''
        elif status == 'in_progress' and not progress_stage:
            cleaned_data['progress_stage'] = 'development'
            progress_stage = 'development'

        if status == 'blocked':
            if not blocked_type:
                self.add_error('blocked_type', 'Blocked tasks require a blocker type.')
            if not blocked_reason:
                self.add_error('blocked_reason', 'Blocked tasks require a reason.')
        else:
            cleaned_data['blocked_type'] = ''
            cleaned_data['blocked_reason'] = ''

        if status == 'done' and task_type == 'development' and progress_stage != 'ready_to_close':
            self.add_error('progress_stage', 'Development tasks can only be marked done from Ready to Close.')

        if self.instance.pk and previous_status == 'done' and status != 'done' and not reopened_reason:
            self.add_error('reopened_reason', 'Reopening a completed task requires a reason.')

        changed_stage = self.instance.pk and previous_stage != progress_stage
        requires_comment = (
            status == 'blocked' or
            changed_stage or
            (self.instance.pk and previous_status == 'done' and status != 'done')
        )
        if requires_comment and not progress_comment:
            self.add_error('progress_comment', 'Please explain this change.')

        return cleaned_data


class TaskCommentForm(StyledModelForm):
    class Meta:
        model = TaskComment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add a comment or progress update'}),
        }


class TaskAttachmentForm(StyledModelForm):
    class Meta:
        model = TaskAttachment
        fields = ['file']


class OffboardMembershipForm(forms.Form):
    replacement_membership = forms.ModelChoiceField(queryset=Membership.objects.none(), required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    replacement_manager = forms.ModelChoiceField(queryset=Membership.objects.none(), required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        membership = kwargs.pop('membership')
        target = kwargs.pop('target')
        super().__init__(*args, **kwargs)
        candidates = membership.organization.memberships.filter(active=True).exclude(pk=target.pk)
        self.fields['replacement_membership'].queryset = candidates
        self.fields['replacement_manager'].queryset = candidates


class LeaveRequestForm(StyledModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        membership = kwargs.pop('membership')
        super().__init__(*args, **kwargs)
        self.membership = membership
        self.fields['leave_type'].queryset = membership.organization.leave_types.all()

    def clean(self):
        cleaned_data = super().clean()
        leave_type = cleaned_data.get('leave_type')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        reason = cleaned_data.get('reason')
        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'End date cannot be before start date.')
        if leave_type and leave_type.reason_required and not reason:
            self.add_error('reason', 'This leave type requires a reason.')
        if start_date and start_date < current_local_date():
            self.add_error('start_date', 'Leave requests must start today or later.')
        return cleaned_data


class LeaveApprovalForm(forms.Form):
    decision = forms.ChoiceField(choices=[('approve', 'Approve'), ('reject', 'Reject')], widget=forms.Select(attrs={'class': 'form-select'}))
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))


class LeaveTypeForm(StyledModelForm):
    class Meta:
        model = LeaveType
        fields = ['name', 'annual_allocation', 'allow_carry_forward', 'reason_required', 'unit']


class HolidayForm(StyledModelForm):
    class Meta:
        model = Holiday
        fields = ['name', 'date', 'location', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class EventForm(StyledModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'event_type', 'starts_at', 'location_or_link', 'audience', 'teams']
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        membership = kwargs.pop('membership')
        super().__init__(*args, **kwargs)
        self.fields['teams'].queryset = membership.organization.teams.all()


class AnnouncementForm(StyledModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'content', 'audience', 'teams', 'publish_at', 'expiry_at']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4}),
            'publish_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'expiry_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        membership = kwargs.pop('membership')
        super().__init__(*args, **kwargs)
        self.fields['teams'].queryset = membership.organization.teams.all()


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user
