from django.contrib import admin

from .models import (
    Announcement,
    AuditLog,
    EmailVerificationToken,
    EmployeeProfile,
    Event,
    Holiday,
    Invitation,
    LeaveLedgerEntry,
    LeaveRequest,
    LeaveType,
    Membership,
    Notification,
    Organization,
    Tag,
    Task,
    TaskActivity,
    TaskAttachment,
    TaskComment,
    Team,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'timezone', 'work_week', 'created_by', 'created_at')
    search_fields = ('name', 'slug')


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'organization', 'user', 'is_owner', 'is_hr', 'is_manager', 'active')
    list_filter = ('organization', 'is_owner', 'is_hr', 'is_manager', 'active')
    search_fields = ('display_name', 'user__username', 'user__email')


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ('membership', 'employee_code', 'designation', 'department', 'joining_date')
    search_fields = ('membership__display_name', 'employee_code', 'designation', 'department')


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'manager', 'created_at')
    filter_horizontal = ('members',)


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'organization', 'role', 'expires_at', 'accepted_at')
    list_filter = ('organization', 'role')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ('name',)


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0
    readonly_fields = ('author', 'body', 'created_at')


class TaskActivityInline(admin.TabularInline):
    model = TaskActivity
    extra = 0
    readonly_fields = ('actor', 'from_status', 'to_status', 'from_progress_stage', 'to_progress_stage', 'comment', 'created_at')


class TaskAttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 0
    readonly_fields = ('uploaded_by', 'original_name', 'file', 'created_at')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('task_key', 'title', 'organization', 'team', 'task_type', 'status', 'progress_stage', 'primary_assignee', 'priority', 'due_date')
    list_filter = ('organization', 'team', 'task_type', 'status', 'progress_stage', 'priority')
    search_fields = ('task_key', 'title', 'description', 'primary_assignee__username')
    filter_horizontal = ('tags', 'collaborators', 'collaborator_memberships')
    inlines = (TaskCommentInline, TaskActivityInline, TaskAttachmentInline)


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'annual_allocation', 'allow_carry_forward', 'reason_required')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('membership', 'leave_type', 'start_date', 'end_date', 'status', 'approver')
    list_filter = ('organization', 'status', 'leave_type')


@admin.register(LeaveLedgerEntry)
class LeaveLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('membership', 'leave_type', 'entry_type', 'days', 'created_at')
    list_filter = ('organization', 'entry_type', 'leave_type')


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'date', 'location')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'event_type', 'starts_at', 'audience')
    filter_horizontal = ('teams',)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'organization', 'publish_at', 'audience')
    filter_horizontal = ('teams',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('membership', 'category', 'title', 'is_read', 'read_at', 'created_at')
    list_filter = ('category', 'is_read')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('organization', 'actor', 'action', 'target_type', 'target_id', 'created_at')


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'expires_at', 'used_at', 'created_at')
