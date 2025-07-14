from datetime import timedelta, datetime
import functools
from rest_framework.response import Response

from api.models import UserSession
from api.settings import SESS_EXP_SECONDS


def validate_password(password):
    MIN_LENGTH = 8
    SPECIAL_CHARACTERS = """!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""

    errors = []
    if len(password) < MIN_LENGTH:
        errors.append(f"Password must be at least {MIN_LENGTH} characters long.")
    if not any(char.isdigit() for char in password):
        errors.append("Password must contain at least one digit.")
    if not any(char.isupper() for char in password):
        errors.append("Password must contain at least one uppercase letter.")
    if not any(char.islower() for char in password):
        errors.append("Password must contain at least one lowercase letter.")
    if not any(char in SPECIAL_CHARACTERS for char in password):
        errors.append("Password must contain at least one special character.")

    return errors


def require_auth(func):
    """
    A decorator to check if the user is authenticated based on their cookies.

    The `user` object is made available in the `request` argument after authentication.

    This refreshes the session token cookie with the response.
    """

    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        token = request.COOKIES.get("account_sess_token")
        if not token:
            return Response(
                {"error": {"general": ["Authentication required"]}}, status=401
            )
        try:
            # Delete sessions where last_used is further than the expiration time
            UserSession.objects.filter(
                last_used__lt=datetime.now() - timedelta(seconds=SESS_EXP_SECONDS)
            ).delete()
            session = UserSession.objects.get(session_token=token)
            session.save()  # To update last_used to now
            request.user = session.user_account
        except UserSession.DoesNotExist:
            response = Response(
                {"error": {"general": ["Authentication required"]}}, status=401
            )
            response.delete_cookie("account_sess_token")
            return response

        response = func(request, *args, **kwargs)
        # Intercept the response to refresh the session token cookie
        response.set_cookie(
            key="account_sess_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="Lax",
            max_age=SESS_EXP_SECONDS,
        )
        return response

    return wrapper
