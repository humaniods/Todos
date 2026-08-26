import os

try:
    from celery import Celery
except ImportError:  # pragma: no cover - fallback for limited local envs
    Celery = None

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'todo_project.settings')

if Celery is not None:
    app = Celery('todo_project')
    app.config_from_object('django.conf:settings', namespace='CELERY')
    app.autodiscover_tasks()
else:
    app = None
