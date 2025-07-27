from datetime import timedelta, datetime
import functools
from rest_framework.response import Response

from django.db import transaction

from api.models import UserAccount, UserSession
from api.settings import SESS_EXP_SECONDS, GENERIC_ERR_RESPONSE

import uuid


def require_auth(func):
    """
    A decorator to check if the user is authenticated based on their cookies.

    The `user` object is made available in the `request` argument after authentication.

    This refreshes the session token cookie with the response.
    """

    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        acct_token = request.COOKIES.get("account_sess_token")
        acct_sess_expired = False
        if acct_token:
            try:
                # Delete non-infinite sessions where last_used is further than the expiration time
                UserSession.objects.filter(
                    is_infinite=False,
                    last_used__lt=datetime.now() - timedelta(seconds=SESS_EXP_SECONDS),
                ).delete()
                with transaction.atomic():
                    session = UserSession.objects.get(session_token=acct_token)
                    session.save()  # To update last_used to now

                # At this point the account is authenticated
                request.user = session.user_account

                response = func(request, *args, **kwargs)
                # Intercept the response to refresh the session token cookie
                response.set_cookie(
                    key="account_sess_token",
                    value=acct_token,
                    httponly=True,
                    secure=True,
                    samesite="Lax",
                    max_age=SESS_EXP_SECONDS,
                )
                return response
            except UserSession.DoesNotExist:
                acct_sess_expired = True
            except Exception as e:
                print(e)
                return GENERIC_ERR_RESPONSE

        # At this point the account session either expired or did not exist
        guest_token = request.COOKIES.get("guest_sess_token")

        if guest_token:
            # Make sure the guest session token exists (it should)
            try:
                with transaction.atomic():
                    session = UserSession.objects.get(session_token=guest_token)
                    session.save()  # Update last_used

                request.user = session.user_account
                # Run the function
                response = func(request, *args, **kwargs)
                response.set_cookie(
                    key="guest_sess_token",
                    value=guest_token,
                    httponly=True,
                    secure=True,
                    samesite="Lax",
                    max_age=SESS_EXP_SECONDS,
                )
            except UserSession.DoesNotExist:
                print(
                    f"Guest session {guest_token} does not exist. Either something went wrong, or someone's doing something weird with the API."
                )
                response = Response(
                    {"error": {"general": ["Guest session expired."]}}, status=401
                )
            except Exception as e:
                print(e)
                return GENERIC_ERR_RESPONSE
        else:
            # Create a guest user with an infinite session
            try:
                with transaction.atomic():
                    guest_account = UserAccount.objects.create(is_guest=True)
                    new_session_token = str(uuid.uuid4())
                    guest_session = UserSession.objects.create(
                        session_token=new_session_token,
                        user_account=guest_account,
                        is_infinite=True,
                    )

                request.user = guest_account
                # Run the function
                response = func(request, *args, **kwargs)
                response.set_cookie(
                    key="guest_sess_token",
                    value=guest_session.session_token,
                    httponly=True,
                    secure=True,
                    samesite="Lax",
                    max_age=SESS_EXP_SECONDS,
                )
            except Exception as e:
                print(e)
                return GENERIC_ERR_RESPONSE

        # Make sure to return a message if the account session expired
        if acct_sess_expired:
            SESS_EXP_MSG = "Account session expired."
            if "message" in response.data:
                response.data["message"].append(SESS_EXP_MSG)
            else:
                response.data["message"] = [SESS_EXP_MSG]
        return response

    return wrapper


def validate_json_input(serializer_class):
    """
    A decorator to validate JSON input data for a view function.

    The `serializer_class` is used to validate the request data.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            serializer = serializer_class(data=request.data)
            if not serializer.is_valid():
                return Response({"error": serializer.errors}, status=400)
            request.validated_data = serializer.validated_data
            return func(request, *args, **kwargs)

        return wrapper

    return decorator


def validate_query_param_input(serializer_class):
    """
    A decorator to validate query parameters for a view function.

    The `serializer_class` is used to validate the query parameters.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            # Parse the query parameters into a dictionary
            # This allows for both single and multiple values for the same key
            query_dict = {}
            for key in request.query_params:
                value = request.query_params.getlist(key)
                if isinstance(value, list):
                    if len(value) == 1:
                        query_dict[key] = value[0]
                    else:
                        query_dict[key] = value
                elif isinstance(value, str):
                    query_dict[key] = value

            serializer = serializer_class(data=query_dict)
            if not serializer.is_valid():
                return Response({"error": serializer.errors}, status=400)
            request.validated_data = serializer.validated_data
            return func(request, *args, **kwargs)

        return wrapper

    return decorator
