from datetime import datetime, timedelta

from celery import shared_task

from api.models import UserSession
from api.settings import LONG_SESS_EXP_SECONDS, SESS_EXP_SECONDS


@shared_task
def session_cleanup():
    """
    Cleans up user sessions that are older than the expiration time for their
    corresponding type.

    Session lifetime is defined in `settings.py`.
    """
    # Regular sessions
    UserSession.objects.filter(
        is_extended=False,
        last_used__lt=datetime.now() - timedelta(seconds=SESS_EXP_SECONDS),
    ).delete()
    # Extended sessions
    UserSession.objects.filter(
        is_extended=True,
        last_used__lt=datetime.now() - timedelta(seconds=LONG_SESS_EXP_SECONDS),
    ).delete()
    # These queries are probably faster separately, since they are individually able to
    # take advantage of the indexes.
