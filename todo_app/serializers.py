from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers

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
    TaskActivity,
    TaskAttachment,
    TaskComment,
    Team,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name']

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs['username'], password=attrs['password'])
        if not user:
            raise serializers.ValidationError('Invalid credentials.')
        attrs['user'] = user
        return attrs


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'timezone', 'work_week', 'leave_year_start', 'created_at']


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    roles = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ['id', 'user', 'display_name', 'roles', 'active', 'joined_at', 'deactivated_at']

    def get_roles(self, obj):
        return obj.role_labels


class TeamSerializer(serializers.ModelSerializer):
    manager = MembershipSerializer(read_only=True)
    manager_id = serializers.PrimaryKeyRelatedField(source='manager', queryset=Membership.objects.all(), write_only=True, required=False, allow_null=True)
    members = serializers.PrimaryKeyRelatedField(queryset=Membership.objects.all(), many=True, required=False)

    class Meta:
        model = Team
        fields = ['id', 'name', 'manager', 'manager_id', 'members', 'created_at']


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ['id', 'email', 'invited_name', 'role', 'team', 'reporting_manager', 'token', 'expires_at', 'accepted_at', 'created_at']
        read_only_fields = ['token', 'expires_at', 'accepted_at', 'created_at']


class TaskAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskAttachment
        fields = ['id', 'original_name', 'file', 'created_at']


class TaskCommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = TaskComment
        fields = ['id', 'author', 'body', 'created_at']


class TaskActivitySerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)

    class Meta:
        model = TaskActivity
        fields = [
            'id',
            'actor',
            'from_status',
            'to_status',
            'from_progress_stage',
            'to_progress_stage',
            'comment',
            'created_at',
        ]


class TaskSerializer(serializers.ModelSerializer):
    comments = TaskCommentSerializer(read_only=True, many=True)
    activities = TaskActivitySerializer(read_only=True, many=True)
    attachments = TaskAttachmentSerializer(read_only=True, many=True)

    class Meta:
        model = Task
        fields = [
            'id', 'organization', 'team', 'task_key', 'title', 'description', 'due_date', 'start_date',
            'expected_next_update', 'priority', 'task_type', 'status', 'progress_stage', 'blocked_type',
            'blocked_reason', 'blocked_from_stage', 'reopened_reason', 'completion_timestamp',
            'primary_assignee', 'primary_membership', 'collaborators', 'collaborator_memberships',
            'comments', 'activities', 'attachments', 'created_at', 'updated_at',
        ]
        read_only_fields = ['organization', 'task_key', 'primary_membership', 'collaborator_memberships', 'completion_timestamp']


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ['id', 'name', 'annual_allocation', 'allow_carry_forward', 'reason_required', 'unit']


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = ['id', 'leave_type', 'start_date', 'end_date', 'reason', 'status', 'approver', 'approver_note', 'created_at', 'updated_at']
        read_only_fields = ['status', 'approver', 'approver_note', 'created_at', 'updated_at']


class LeaveLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveLedgerEntry
        fields = ['id', 'entry_type', 'days', 'note', 'created_at']


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ['id', 'name', 'date', 'location', 'description']


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ['id', 'title', 'description', 'event_type', 'starts_at', 'location_or_link', 'audience', 'teams', 'created_at']
        read_only_fields = ['created_at']


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ['id', 'title', 'content', 'audience', 'teams', 'publish_at', 'expiry_at', 'created_at']
        read_only_fields = ['created_at']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'category', 'title', 'body', 'url', 'is_read', 'read_at', 'created_at']
