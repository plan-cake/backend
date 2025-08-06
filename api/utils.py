import functools
import logging
import uuid
from datetime import datetime, timedelta

from django.db import DatabaseError, transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.models import UserAccount, UserSession
from api.settings import (
    GENERIC_ERR_RESPONSE,
    LONG_SESS_EXP_SECONDS,
    REST_FRAMEWORK,
    SESS_EXP_SECONDS,
)

logger = logging.getLogger("api")


class APIMetadata:
    """
    Holds metadata to be used for documentation.
    """

    def __init__(self):
        self.method = None
        self.input_type = None
        self.input_serializer_class = None
        self.output_serializer_class = None
        self.rate_limit = None
        self.min_auth_required = None


def get_metadata(func):
    """
    For use with documentation.

    Returns the APIMetadata class for the provided function, to be added to. If it doesn't
    exist, one will be created.
    """
    if not hasattr(func, "metadata"):
        func.metadata = APIMetadata()
    return func.metadata


def api_endpoint(method):
    """
    Defines an API endpoint that uses a single method type.

    **This must be the outer-most decorator for the view function to work properly.**
    """

    def decorator(func):
        drf_view = api_view([method])(func)
        metadata = get_metadata(func)
        metadata.method = method
        drf_view.metadata = metadata
        # Check if the endpoint has an output serializer
        if not metadata.output_serializer_class:
            logger.warning(
                "No output serializer defined for function: %s",
                func.__name__,
            )
        return drf_view

    return decorator


def get_session(token):
    """
    Retrieves a session by its token, ensuring it is still valid.
    """
    return (
        UserSession.objects.filter(session_token=token)
        .filter(
            (
                Q(is_extended=True)
                & Q(
                    last_used__gte=datetime.now()
                    - timedelta(seconds=LONG_SESS_EXP_SECONDS)
                )
            )
            | (
                Q(is_extended=False)
                & Q(last_used__gte=datetime.now() - timedelta(seconds=SESS_EXP_SECONDS))
            )
        )
        .first()
    )


class GuestAccountCreationThrottle(AnonRateThrottle):
    scope = "guest_account_creation"


def require_auth(func):
    """
    A decorator to check if the user is authenticated (either with an account or as a
    guest) based on their cookies.

    If the user is not authenticated, a guest account will be created for them. If the
    supplied guest account/session does not exist, a new one will be created.

    The `user` object is made available in the `request` argument after authentication.

    If authenticated, this refreshes the session token cookie with the response.
    """

    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        acct_token = request.COOKIES.get("account_sess_token")
        acct_sess_expired = False
        if acct_token:
            logger.debug("Account session token: %s", acct_token)
            try:
                with transaction.atomic():
                    session = get_session(acct_token)
                    if not session:
                        # To break out of the rest of the logic
                        raise UserSession.DoesNotExist
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
                    max_age=(
                        LONG_SESS_EXP_SECONDS
                        if session.is_extended
                        else SESS_EXP_SECONDS
                    ),
                )
                return response
            except UserSession.DoesNotExist:
                logger.info("Account session expired.")
                acct_sess_expired = True
            except DatabaseError as e:
                logger.db_error(e)
                return GENERIC_ERR_RESPONSE
            except Exception as e:
                logger.error(e)
                return GENERIC_ERR_RESPONSE

        # At this point the account session either expired or did not exist
        guest_token = request.COOKIES.get("guest_sess_token")

        if guest_token:
            logger.debug("Guest session token: %s", guest_token)
            # Make sure the guest session token exists (it should)
            try:
                with transaction.atomic():
                    session = get_session(guest_token)
                    if not session:
                        raise UserSession.DoesNotExist
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
                    max_age=LONG_SESS_EXP_SECONDS,
                )
            except UserSession.DoesNotExist:
                logger.info("Guest session expired. Creating a new guest account...")
                # Check guest creation rate limit
                throttle = GuestAccountCreationThrottle()
                if not throttle.allow_request(request, None):
                    logger.warning(
                        f"Guest creation limit ({throttle.get_rate()}) reached."
                    )
                    return Response(
                        {
                            "error": {
                                "general": [
                                    f"Guest creation limit ({throttle.get_rate()}) reached. Make sure cookies are enabled for this site, and try again later."
                                ]
                            }
                        },
                        status=429,
                    )
                # Create a new guest user
                try:
                    with transaction.atomic():
                        guest_account = UserAccount.objects.create(is_guest=True)
                        new_session_token = str(uuid.uuid4())
                        guest_session = UserSession.objects.create(
                            session_token=new_session_token,
                            user_account=guest_account,
                            is_extended=True,
                        )
                    logger.debug(
                        "New guest session token: %s", guest_session.session_token
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
                        max_age=LONG_SESS_EXP_SECONDS,
                    )
                except DatabaseError as e:
                    logger.db_error(e)
                    return GENERIC_ERR_RESPONSE
                except Exception as e:
                    logger.error(e)
                    return GENERIC_ERR_RESPONSE
            except Exception as e:
                logger.error(e)
                return GENERIC_ERR_RESPONSE
        else:
            # Check guest creation rate limit
            throttle = GuestAccountCreationThrottle()
            if not throttle.allow_request(request, None):
                logger.warning(f"Guest creation limit ({throttle.get_rate()}) reached.")
                return Response(
                    {
                        "error": {
                            "general": [
                                f"Guest creation limit ({throttle.get_rate()}) reached. Make sure cookies are enabled for this site, and try again later."
                            ]
                        }
                    },
                    status=429,
                )
            # Create a guest user with an extended session
            try:
                with transaction.atomic():
                    guest_account = UserAccount.objects.create(is_guest=True)
                    new_session_token = str(uuid.uuid4())
                    guest_session = UserSession.objects.create(
                        session_token=new_session_token,
                        user_account=guest_account,
                        is_extended=True,
                    )
                logger.debug("New guest session token: %s", guest_session.session_token)

                request.user = guest_account
                # Run the function
                response = func(request, *args, **kwargs)
                response.set_cookie(
                    key="guest_sess_token",
                    value=guest_session.session_token,
                    httponly=True,
                    secure=True,
                    samesite="Lax",
                    max_age=LONG_SESS_EXP_SECONDS,
                )
            except DatabaseError as e:
                logger.db_error(e)
                return GENERIC_ERR_RESPONSE
            except Exception as e:
                logger.error(e)
                return GENERIC_ERR_RESPONSE

        # Make sure to return a message if the account session expired
        if acct_sess_expired:
            SESS_EXP_MSG = "Account session expired."
            if "message" in response.data:
                response.data["message"].append(SESS_EXP_MSG)
            else:
                response.data["message"] = [SESS_EXP_MSG]
            response.delete_cookie("account_sess_token")
        return response

    get_metadata(wrapper).min_auth_required = "Guest"
    return wrapper


def require_account_auth(func):
    """
    A decorator to check if the user is authenticated **strictly with an account** based
    on their cookies.

    If the user is not authenticated, an error message will be returned.

    The `user` object is made available in the `request` argument after authentication.

    If authenticated, this refreshes the session token cookie with the response.
    """

    @functools.wraps(func)
    def wrapper(request, *args, **kwargs):
        acct_token = request.COOKIES.get("account_sess_token")
        logger.debug("Account session token: %s", acct_token)

        BAD_AUTH_RESPONSE = Response(
            {"error": {"general": ["Account required."]}}, status=401
        )

        if acct_token:
            try:
                with transaction.atomic():
                    session = get_session(acct_token)
                    if not session:
                        raise UserSession.DoesNotExist
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
                    max_age=(
                        LONG_SESS_EXP_SECONDS
                        if session.is_extended
                        else SESS_EXP_SECONDS
                    ),
                )
                return response
            except UserSession.DoesNotExist:
                logger.info("Account session expired.")
                return BAD_AUTH_RESPONSE
            except DatabaseError as e:
                logger.db_error(e)
                return GENERIC_ERR_RESPONSE
            except Exception as e:
                logger.error(e)
                return GENERIC_ERR_RESPONSE
        else:
            return BAD_AUTH_RESPONSE

    get_metadata(wrapper).min_auth_required = "User Account"
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

        metadata = get_metadata(wrapper)
        metadata.input_type = "JSON Body"
        metadata.input_serializer_class = serializer_class
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

        metadata = get_metadata(wrapper)
        metadata.input_type = "Query Parameters"
        metadata.input_serializer_class = serializer_class
        return wrapper

    return decorator


def validate_error_format(data, input_serializer_class):
    """
    A helper function to make sure that error messages are returned in whatever crazy
    format I decided to use for this project.

    Expected format:
    {
        "error": {
            "general/[input serializer field name]": [
                "Error message",
                ...
            ],
            ...
        }
    }
    """

    def log_error_msg_error(message):
        logger.error("Error message validation error: %s", message)

    if not isinstance(data, dict):
        log_error_msg_error("Response must be a dictionary.")

    if "error" not in data or not isinstance(data["error"], dict):
        log_error_msg_error("Response must contain an 'error' dictionary.")

    if input_serializer_class:
        for field_name, value in data["error"].items():
            if field_name not in input_serializer_class().fields:
                if field_name != "general":
                    log_error_msg_error(
                        f"{field_name} must be a field name from the input serializer."
                    )
            if not isinstance(value, list):
                log_error_msg_error(f"{field_name} must be a list.")
            if not all(isinstance(item, str) for item in value):
                log_error_msg_error(f"All items in {field_name} must be strings.")
    else:
        for field_name, value in data["error"].items():
            if field_name != "general":
                log_error_msg_error(
                    f"{field_name} must be named 'general' if no input serializer is provided."
                )
            if not isinstance(value, list):
                log_error_msg_error(f"{field_name} must be a list.")


class MessageOutputSerializer(serializers.Serializer):
    message = serializers.ListField(child=serializers.CharField())


def validate_output(serializer_class):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            response = func(request, *args, **kwargs)
            if isinstance(response, Response):
                if 200 <= response.status_code < 300:
                    serializer = serializer_class(data=response.data)
                    if serializer.is_valid():
                        response.data = serializer.validated_data
                        return response
                    else:
                        print(serializer.errors)
                        return GENERIC_ERR_RESPONSE
                else:
                    validate_error_format(
                        response.data, get_metadata(wrapper).input_serializer_class
                    )
                    # If the format is bad, just print errors to the log and move on
                    # We don't want errors causing errors to cause problems in prod
                    return response
            else:
                logger.critical("Response is not a valid Response object.")
                return GENERIC_ERR_RESPONSE

        get_metadata(wrapper).output_serializer_class = serializer_class
        return wrapper

    return decorator


def get_rate_limit(scope):
    return REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}).get(scope, None)


def rate_limit(
    throttle_class, error_message="Rate limit ({rate}) exceeded. Try again later."
):
    """
    A decorator that takes a throttle class and limits the endpoint accordingly.

    An optional message can be passed, which can include the `{rate}` placeholder to
    dynamically insert the rate limit value.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            throttle = throttle_class()
            if not throttle.allow_request(request, None):
                msg = error_message
                if "{rate}" in msg:
                    msg = msg.replace("{rate}", throttle.get_rate())
                logger.warning(msg)
                return Response(
                    {"error": {"general": [msg]}},
                    status=429,
                )
            return func(request, *args, **kwargs)

        get_metadata(wrapper).rate_limit = get_rate_limit(throttle_class.scope)
        return wrapper

    return decorator
