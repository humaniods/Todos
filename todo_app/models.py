from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone as dj_timezone
from django.utils.text import slugify


class Organization(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    timezone = models.CharField(max_length=64, default='Asia/Kolkata')
    work_week = models.CharField(max_length=32, default='Mon-Fri')
    leave_year_start = models.DateField(default=dj_timezone.localdate)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_organizations')
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or 'organization'
            slug = base_slug
            suffix = 1
            while Organization.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                suffix += 1
                slug = f'{base_slug}-{suffix}'
            self.slug = slug
        super().save(*args, **kwargs)


class Membership(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    display_name = models.CharField(max_length=255)
    is_employee = models.BooleanField(default=True)
    is_manager = models.BooleanField(default=False)
    is_hr = models.BooleanField(default=False)
    is_owner = models.BooleanField(default=False)
    reporting_manager = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='direct_reports',
    )
    active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=dj_timezone.now, editable=False)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('organization', 'user')
        ordering = ['display_name', 'user__username']

    def __str__(self):
        return f'{self.display_name} @ {self.organization}'

    @property
    def role_labels(self):
        labels = ['Employee']
        if self.is_manager:
            labels.append('Manager')
        if self.is_hr:
            labels.append('HR')
        if self.is_owner:
            labels.append('Owner')
        return labels


class EmployeeProfile(models.Model):
    membership = models.OneToOneField(Membership, on_delete=models.CASCADE, related_name='profile')
    employee_code = models.CharField(max_length=50, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    joining_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['employee_code', 'membership__display_name']

    def __str__(self):
        return f'Profile for {self.membership.display_name}'


class Team(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=255)
    manager = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='managed_teams',
    )
    members = models.ManyToManyField(Membership, blank=True, related_name='teams')
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        unique_together = ('organization', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class Invitation(models.Model):
    ROLE_CHOICES = [
        ('employee', 'Employee'),
        ('manager', 'Manager'),
        ('hr', 'HR'),
        ('owner', 'Owner'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    invited_name = models.CharField(max_length=255)
    invited_by = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='sent_invitations')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL, related_name='invitations')
    reporting_manager = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='managed_invitations',
    )
    token = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} for {self.organization}'


class Tag(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Task(models.Model):
    PRIORITY_CHOICES = [('Low', 'Low'), ('Medium', 'Medium'), ('High', 'High')]
    TASK_TYPE_CHOICES = [('general', 'General'), ('development', 'Development')]
    STATUS_CHOICES = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('blocked', 'Blocked'),
        ('done', 'Done'),
    ]
    PROGRESS_STAGE_CHOICES = [
        ('', 'No checkpoint'),
        ('development', 'Development'),
        ('dev_deployment_pending', 'Dev Deployment Pending'),
        ('qa_testing_pending', 'QA Testing Pending'),
        ('production_deployment_pending', 'Production Deployment Pending'),
        ('production_testing_pending', 'Production Testing Pending'),
        ('ready_to_close', 'Ready to Close'),
    ]
    BLOCKER_TYPE_CHOICES = [
        ('', 'No blocker'),
        ('dependency', 'Dependency'),
        ('review', 'Review'),
        ('access', 'Access'),
        ('clarification', 'Clarification'),
        ('bug', 'Bug'),
        ('other', 'Other'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='tasks', null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, related_name='tasks', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    primary_assignee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='primary_tasks')
    primary_membership = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_tasks',
    )
    collaborators = models.ManyToManyField(User, blank=True, related_name='collaborative_tasks')
    collaborator_memberships = models.ManyToManyField(Membership, blank=True, related_name='collaborative_task_memberships')
    task_key = models.CharField(max_length=32, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    expected_next_update = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default='general')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    progress_stage = models.CharField(max_length=40, choices=PROGRESS_STAGE_CHOICES, blank=True, default='')
    blocked_type = models.CharField(max_length=20, choices=BLOCKER_TYPE_CHOICES, blank=True, default='')
    blocked_reason = models.TextField(blank=True)
    blocked_from_stage = models.CharField(max_length=40, blank=True, default='')
    reopened_reason = models.TextField(blank=True)
    completion_timestamp = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        ordering = ['status', 'due_date', '-updated_at']
        unique_together = ('organization', 'task_key')

    def __str__(self):
        return self.title


def task_attachment_upload_to(instance, filename):
    organization_id = instance.task.organization_id or 'shared'
    task_key = instance.task.task_key or f'task-{instance.task_id}'
    return f'attachments/org-{organization_id}/{task_key}/{filename}'


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_comments')
    body = models.TextField()
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.author} on {self.task}'


class TaskActivity(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_activities')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    from_progress_stage = models.CharField(max_length=40, blank=True)
    to_progress_stage = models.CharField(max_length=40, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.task} by {self.actor}'


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_attachments')
    file = models.FileField(upload_to=task_attachment_upload_to)
    original_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.original_name


class LeaveType(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='leave_types')
    name = models.CharField(max_length=100)
    annual_allocation = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    allow_carry_forward = models.BooleanField(default=False)
    reason_required = models.BooleanField(default=False)
    unit = models.CharField(max_length=16, default='days')

    class Meta:
        unique_together = ('organization', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='leave_requests')
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name='leave_requests')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approver = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_leave_requests',
    )
    approver_note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.membership} {self.start_date} - {self.end_date}'


class LeaveLedgerEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ('allocation', 'Allocation'),
        ('carry_forward', 'Carry Forward'),
        ('approved_leave', 'Approved Leave'),
        ('cancellation_reversal', 'Cancellation Reversal'),
        ('hr_correction', 'HR Correction'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='leave_ledger_entries')
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='leave_ledger_entries')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name='ledger_entries')
    leave_request = models.ForeignKey(
        LeaveRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ledger_entries',
    )
    entry_type = models.CharField(max_length=30, choices=ENTRY_TYPE_CHOICES)
    days = models.DecimalField(max_digits=6, decimal_places=1)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_leave_ledger_entries',
    )
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['-created_at']


class Holiday(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='holidays')
    name = models.CharField(max_length=255)
    date = models.DateField()
    location = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ('organization', 'name', 'date')
        ordering = ['date']

    def __str__(self):
        return self.name


class Event(models.Model):
    AUDIENCE_CHOICES = [
        ('org', 'Entire organization'),
        ('teams', 'Specific teams'),
    ]
    TYPE_CHOICES = [
        ('meeting', 'Meeting'),
        ('celebration', 'Celebration'),
        ('training', 'Training'),
        ('other', 'Other'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other')
    starts_at = models.DateTimeField()
    location_or_link = models.CharField(max_length=255, blank=True)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='org')
    teams = models.ManyToManyField(Team, blank=True, related_name='events')
    created_by = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='created_events')
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['starts_at']


class Announcement(models.Model):
    AUDIENCE_CHOICES = [
        ('org', 'Entire organization'),
        ('teams', 'Specific teams'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=255)
    content = models.TextField()
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='org')
    teams = models.ManyToManyField(Team, blank=True, related_name='announcements')
    publish_at = models.DateTimeField(default=dj_timezone.now)
    expiry_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='created_announcements')
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['-publish_at']


class Notification(models.Model):
    CATEGORY_CHOICES = [
        ('invitation', 'Invitation'),
        ('task', 'Task'),
        ('leave', 'Leave'),
        ('event', 'Event'),
        ('announcement', 'Announcement'),
        ('admin', 'Administrative'),
    ]

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='notifications')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['is_read', '-created_at']


class AuditLog(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)

    class Meta:
        ordering = ['-created_at']


class EmailVerificationToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verification_tokens')
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=dj_timezone.now, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Email verification for {self.user.username}'
