import os
import tempfile
from datetime import timedelta


def configure_streamlit_environment():
    if 'SQLITE_PATH' not in os.environ:
        os.environ['SQLITE_PATH'] = os.path.join(tempfile.gettempdir(), 'officediary-streamlit.sqlite3')

    try:
        import streamlit as st
    except Exception:
        return

    secret_keys = [
        'DJANGO_SECRET_KEY',
        'DJANGO_DEBUG',
        'DJANGO_ALLOWED_HOSTS',
        'SQLITE_PATH',
        'DISCORD_CLIENT_ID',
        'DISCORD_CLIENT_SECRET',
        'DISCORD_REDIRECT_URI',
    ]
    for key in secret_keys:
        value = st.secrets.get(key)
        if value not in (None, '') and key not in os.environ:
            os.environ[key] = str(value)


def bootstrap_django():
    configure_streamlit_environment()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'todo_project.settings')

    import django

    django.setup()


def ensure_demo_ready():
    bootstrap_django()

    from django.core.management import call_command

    from todo_app.models import Organization

    call_command('migrate', interactive=False, run_syncdb=True, verbosity=0)
    if not Organization.objects.exists():
        call_command('seed_demo_data', verbosity=0)


def organization_snapshot(organization_id, viewer_membership_id):
    bootstrap_django()

    from django.db.models import Count
    from django.utils import timezone

    from todo_app.models import Announcement, Event, Holiday, LeaveRequest, Membership, Task
    from todo_app.services import leave_balance_summary, visible_tasks_for_membership

    organization = (
        Membership.objects.select_related('organization')
        .get(pk=viewer_membership_id, organization_id=organization_id)
        .organization
    )
    viewer = (
        Membership.objects.select_related('user', 'organization', 'reporting_manager')
        .get(pk=viewer_membership_id, organization_id=organization_id)
    )
    members = list(
        organization.memberships.filter(active=True)
        .select_related('user', 'reporting_manager')
        .order_by('display_name')
    )
    tasks = list(
        visible_tasks_for_membership(viewer)
        .filter(organization=organization)
        .select_related('team', 'primary_membership', 'user')
        .prefetch_related('collaborator_memberships', 'comments', 'activities')
        .distinct()
    )
    status_counts = list(
        Task.objects.filter(organization=organization)
        .values('status')
        .annotate(total=Count('id'))
        .order_by('status')
    )
    today = timezone.localdate()
    return {
        'organization': organization,
        'viewer': viewer,
        'members': members,
        'tasks': tasks,
        'status_counts': status_counts,
        'leave_summary': leave_balance_summary(viewer),
        'pending_leave_requests': list(
            LeaveRequest.objects.filter(organization=organization, status='pending')
            .select_related('membership', 'leave_type', 'approver')
            .order_by('-created_at')
        ),
        'holidays': list(Holiday.objects.filter(organization=organization, date__gte=today).order_by('date')[:8]),
        'events': list(Event.objects.filter(organization=organization, starts_at__date__gte=today).order_by('starts_at')[:8]),
        'announcements': list(
            Announcement.objects.filter(organization=organization, publish_at__lte=timezone.now())
            .select_related('created_by')
            .order_by('-publish_at')[:6]
        ),
    }


def create_task(
    *,
    organization_id,
    actor_membership_id,
    assignee_membership_id,
    title,
    description,
    priority,
    task_type,
    due_date,
    start_date,
    expected_next_update,
    team_id=None,
    collaborator_membership_ids=None,
):
    bootstrap_django()

    from django.db import transaction

    from todo_app.models import Membership, Task, Team
    from todo_app.services import create_audit_log, create_notification, next_task_key, record_task_activity

    collaborator_membership_ids = collaborator_membership_ids or []

    with transaction.atomic():
        actor = Membership.objects.select_related('organization', 'user').get(pk=actor_membership_id, organization_id=organization_id)
        assignee = Membership.objects.select_related('user').get(pk=assignee_membership_id, organization_id=organization_id)
        team = Team.objects.filter(pk=team_id, organization_id=organization_id).first() if team_id else None
        task = Task.objects.create(
            organization=actor.organization,
            team=team,
            user=actor.user,
            primary_assignee=assignee.user,
            primary_membership=assignee,
            task_key=next_task_key(actor.organization),
            title=title,
            description=description,
            due_date=due_date,
            start_date=start_date,
            expected_next_update=expected_next_update,
            priority=priority,
            task_type=task_type,
            status='todo',
        )
        if collaborator_membership_ids:
            collaborators = list(
                Membership.objects.filter(
                    pk__in=collaborator_membership_ids,
                    organization_id=organization_id,
                    active=True,
                ).select_related('user')
            )
            task.collaborator_memberships.set(collaborators)
            task.collaborators.set([member.user for member in collaborators])
        record_task_activity(task, actor, '', '', 'Task created from Streamlit workspace.')
        create_notification(
            assignee,
            'task',
            f'Assigned {task.task_key}',
            task.title,
            '/tasks/',
        )
        create_audit_log(actor.organization, actor, 'task_created', task, task.title)
    return task.pk


def update_task(
    *,
    organization_id,
    actor_membership_id,
    task_id,
    status,
    progress_stage,
    blocked_type,
    blocked_reason,
    reopened_reason,
    comment,
):
    bootstrap_django()

    from django.db import transaction
    from django.utils import timezone

    from todo_app.models import Membership, Task, TaskComment
    from todo_app.services import create_audit_log, record_task_activity

    with transaction.atomic():
        actor = Membership.objects.select_related('organization', 'user').get(pk=actor_membership_id, organization_id=organization_id)
        task = Task.objects.select_related('primary_membership').get(pk=task_id, organization_id=organization_id)
        previous_status = task.status
        previous_stage = task.progress_stage
        task.status = status
        task.progress_stage = progress_stage
        task.blocked_type = blocked_type if status == 'blocked' else ''
        task.blocked_reason = blocked_reason if status == 'blocked' else ''
        task.reopened_reason = reopened_reason if previous_status == 'done' and status != 'done' else ''
        if status == 'done' and previous_status != 'done':
            task.completion_timestamp = timezone.now()
        elif status != 'done':
            task.completion_timestamp = None
        task.save(
            update_fields=[
                'status',
                'progress_stage',
                'blocked_type',
                'blocked_reason',
                'reopened_reason',
                'completion_timestamp',
                'updated_at',
            ]
        )
        if comment.strip():
            TaskComment.objects.create(task=task, author=actor.user, body=comment.strip())
        record_task_activity(task, actor, previous_status, previous_stage, comment.strip())
        create_audit_log(actor.organization, actor, 'task_updated', task, f'{task.task_key}: {task.status}')
    return task.pk


def submit_leave(organization_id, membership_id, leave_type_id, start_date, end_date, reason):
    bootstrap_django()

    from todo_app.models import LeaveType, Membership
    from todo_app.services import submit_leave_request

    membership = Membership.objects.get(pk=membership_id, organization_id=organization_id)
    leave_type = LeaveType.objects.get(pk=leave_type_id, organization_id=organization_id)
    return submit_leave_request(membership, leave_type, start_date, end_date, reason)


def decide_leave(organization_id, approver_membership_id, leave_request_id, approve, note):
    bootstrap_django()

    from todo_app.models import LeaveRequest, Membership
    from todo_app.services import approve_leave_request

    approver = Membership.objects.get(pk=approver_membership_id, organization_id=organization_id)
    leave_request = LeaveRequest.objects.select_related('membership', 'leave_type').get(
        pk=leave_request_id,
        organization_id=organization_id,
    )
    return approve_leave_request(leave_request, approver, approve=approve, note=note)


def available_leave_types(organization_id):
    bootstrap_django()

    from todo_app.models import LeaveType

    return list(LeaveType.objects.filter(organization_id=organization_id).order_by('name'))


def task_status_labels():
    return {
        'todo': 'To Do',
        'in_progress': 'In Progress',
        'blocked': 'Blocked',
        'done': 'Done',
    }


def progress_stage_labels():
    return {
        '': 'No checkpoint',
        'development': 'Development',
        'dev_deployment_pending': 'Dev Deployment Pending',
        'qa_testing_pending': 'QA Testing Pending',
        'production_deployment_pending': 'Production Deployment Pending',
        'production_testing_pending': 'Production Testing Pending',
        'ready_to_close': 'Ready to Close',
    }


def blocker_labels():
    return {
        '': 'No blocker',
        'dependency': 'Dependency',
        'review': 'Review',
        'access': 'Access',
        'clarification': 'Clarification',
        'bug': 'Bug',
        'other': 'Other',
    }


def overdue_tasks(tasks):
    bootstrap_django()

    from django.utils import timezone

    today = timezone.localdate()
    return [task for task in tasks if task.due_date and task.due_date < today and task.status != 'done']


def upcoming_task_window(tasks, days=7):
    bootstrap_django()

    from django.utils import timezone

    today = timezone.localdate()
    boundary = today + timedelta(days=days)
    return [task for task in tasks if task.due_date and today <= task.due_date <= boundary and task.status != 'done']
