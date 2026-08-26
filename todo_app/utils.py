from django.conf import settings
from django.utils import timezone


def current_local_date():
    if settings.USE_TZ:
        return timezone.localdate()
    return timezone.now().date()
