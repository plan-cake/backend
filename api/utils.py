from datetime import timedelta, datetime
import functools
from rest_framework.response import Response

from api.models import UserSession
from api.settings import SESS_EXP_SECONDS


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
                {"error": {"general": ["Authentication required."]}}, status=401
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
                {"error": {"general": ["Session expired."]}}, status=401
            )
            response.delete_cookie("account_sess_token")
            return response
        except Exception as e:
            print(e)
            return Response(
                {"error": {"general": ["An unknown error has occurred."]}}, status=500
            )

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
