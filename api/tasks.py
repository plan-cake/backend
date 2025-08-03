from datetime import datetime, timedelta

from celery import shared_task

from api.models import UserAccount, UserSession
from api.settings import LONG_SESS_EXP_SECONDS, SESS_EXP_SECONDS


def session_cleanup():
    """
    Cleans up sessions that are older than the expiration time for their corresponding
    type.

    Session lifetime is defined for each type in `settings.py`.
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


def guest_cleanup():
    """
    Removes guest users that no longer have any sessions.
    """
    UserAccount.objects.filter(is_guest=True, session_tokens__isnull=True).delete()


def unverified_user_cleanup():
    pass


def password_reset_token_cleanup():
    pass


@shared_task
def daily_cleanup():
    """
    Cleans up expired sessions, guests, unverified users, and password reset tokens.
    """
    session_cleanup()
    guest_cleanup()
    unverified_user_cleanup()
    password_reset_token_cleanup()
