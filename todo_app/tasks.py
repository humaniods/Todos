from datetime import timedelta

from django.core.mail import send_mail
from django.utils import timezone

from todo_project.celery import app

from .models import Notification, Task
from .utils import current_local_date


def _task(func):
    return app.task(func) if app is not None else func


@_task
def send_notification_email(subject, body, recipient):
    send_mail(subject, body, None, [recipient], fail_silently=True)


@_task
def notify_due_tasks():
    today = current_local_date()
    tomorrow = today + timedelta(days=1)
    for task in Task.objects.filter(due_date__in=[tomorrow, today], status__in=['todo', 'in_progress', 'blocked']).select_related('primary_assignee'):
        if task.primary_assignee.email:
            if app is not None:
                send_notification_email.delay(
                    f'Task reminder: {task.task_key}',
                    f'{task.title} is due on {task.due_date}.',
                    task.primary_assignee.email,
                )
            else:
                send_notification_email(
                    f'Task reminder: {task.task_key}',
                    f'{task.title} is due on {task.due_date}.',
                    task.primary_assignee.email,
                )
