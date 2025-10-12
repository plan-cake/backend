import logging
import uuid
from datetime import datetime, timedelta

import bcrypt
from django.core.mail import send_mail
from django.db import DatabaseError, transaction
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.auth.serializers import (
    EmailSerializer,
    EmailVerifySerializer,
    LoginSerializer,
    PasswordResetSerializer,
    PasswordSerializer,
    RegisterAccountSerializer,
)
from api.auth.utils import validate_password
from api.models import (
    PasswordResetToken,
    UnverifiedUserAccount,
    UserAccount,
    UserLogin,
    UserSession,
)
from api.settings import (
    ACCOUNT_COOKIE_NAME,
    BASE_URL,
    EMAIL_CODE_EXP_SECONDS,
    GENERIC_ERR_RESPONSE,
    LONG_SESS_EXP_SECONDS,
    PWD_RESET_EXP_SECONDS,
    SEND_EMAILS,
    SESS_EXP_SECONDS,
)
from api.utils import (
    MessageOutputSerializer,
    api_endpoint,
    get_session,
    rate_limit,
    require_account_auth,
    validate_json_input,
    validate_output,
)

logger = logging.getLogger("api")


class RegisterAccountThrottle(AnonRateThrottle):
    scope = "user_account_creation"


@api_endpoint("POST")
@rate_limit(
    RegisterAccountThrottle, "Account creation limit reached ({rate}). Try again later."
)
@validate_json_input(RegisterAccountSerializer)
@validate_output(MessageOutputSerializer)
def register(request):
    """
    Registers a new user account as an "unverified user" that cannot be used until the
    email address is verified.

    If the email address is available, it will send an email with a link to verify.

    If the email address is already used for an unverified user, it will update the
    verification code and send a new email.

    If the email address is already used for an account and verified, it will let the user
    know that via email.
    """
    email = request.validated_data.get("email")
    password = request.validated_data.get("password")

    try:
        # Validate the password first
        if errors := validate_password(password):
            return Response({"error": {"password": errors}}, status=400)
        pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Check if the email already exists
        if UserAccount.objects.filter(email=email).exists():
            logger.info("Email %s is already in use!", email)
            if SEND_EMAILS:
                send_mail(
                    subject="Plancake - Email in Use",
                    message=f"Looks like your email was already used for a Plancake account.\n\nNot you? Nothing to worry about, just ignore this email.",
                    from_email=None,  # Use the default from settings
                    recipient_list=[email],
                    fail_silently=False,
                )
        else:
            # Create an unverified user account
            ver_code = str(uuid.uuid4())
            with transaction.atomic():
                UnverifiedUserAccount.objects.filter(email=email).delete()
                UnverifiedUserAccount.objects.create(
                    verification_code=ver_code,
                    email=email,
                    password_hash=pwd_hash,
                )
            logger.debug("Verification code for %s: %s", email, ver_code)

            if SEND_EMAILS:
                send_mail(
                    subject="Plancake - Email Verification",
                    message=f"Welcome to Plancake!\n\nClick this link to verify your email:\n{BASE_URL}/verify-email?code={ver_code}\n\nNot you? Nothing to worry about, just ignore this email.",
                    from_email=None,  # Use the default from settings
                    recipient_list=[email],
                    fail_silently=False,
                )

        return Response(
            {"message": ["An email has been sent to your address for verification."]},
            status=200,
        )

    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE


class ResendEmailThrottle(AnonRateThrottle):
    scope = "resend_email"


@api_endpoint("POST")
@rate_limit(
    ResendEmailThrottle, "Resend email limit reached ({rate}). Try again later."
)
@validate_json_input(EmailSerializer)
@validate_output(MessageOutputSerializer)
def resend_register_email(request):
    """
    Attempts to resend the verification email for an unverified user account.

    If the email address is either already used for a verified user account, or not
    associated with an unverified user account, nothing will happen.

    Ideally, the frontend would not allow the user to call this endpoint if the
    verification code would already have expired. Instead, the user should be prompted to
    register again.
    """
    email = request.validated_data.get("email")

    try:
        unverified_user = UnverifiedUserAccount.objects.get(
            email=email,
            created_at__gte=datetime.now() - timedelta(seconds=EMAIL_CODE_EXP_SECONDS),
        )
        logger.debug(
            "Verification code for %s: %s",
            email,
            unverified_user.verification_code,
        )

        if SEND_EMAILS:
            send_mail(
                subject="Plancake - Email Verification",
                message=f"Welcome to Plancake!\n\nClick this link to verify your email:\n{BASE_URL}/verify-email?code={unverified_user.verification_code}\n\nNot you? Nothing to worry about, just ignore this email.",
                from_email=None,  # Use the default from settings
                recipient_list=[email],
                fail_silently=False,
            )

    except UnverifiedUserAccount.DoesNotExist:
        logger.info("Unverified user with email %s does not exist!", email)
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response({"message": ["Verification email resent."]}, status=200)


@api_endpoint("POST")
@validate_json_input(EmailVerifySerializer)
@validate_output(MessageOutputSerializer)
def verify_email(request):
    """
    Verifies the email address of an unverified user account.

    If the verification code is valid, it creates a verified user account with the
    information given when initially registering.

    This endpoint does NOT automatically log in the user after verifying.
    """
    ver_code = request.validated_data.get("verification_code")

    try:
        unverified_user = UnverifiedUserAccount.objects.get(
            verification_code=ver_code,
            created_at__gte=datetime.now() - timedelta(seconds=EMAIL_CODE_EXP_SECONDS),
        )

        with transaction.atomic():
            # Create the user account
            UserAccount.objects.create(
                email=unverified_user.email,
                password_hash=unverified_user.password_hash,
                is_guest=False,
            )
            # Delete the unverified user account
            unverified_user.delete()
        logger.info("Account successfully created for %s.", unverified_user.email)

    except UnverifiedUserAccount.DoesNotExist:
        logger.info("Verification code is invalid.")
        return Response(
            {"error": {"verification_code": ["Invalid verification code."]}}, status=404
        )
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response({"message": ["Email verified successfully."]}, status=200)


class LoginThrottle(AnonRateThrottle):
    scope = "login"


@api_endpoint("POST")
@rate_limit(LoginThrottle, "Login limit reached ({rate}). Try again later.")
@validate_json_input(LoginSerializer)
@validate_output(MessageOutputSerializer)
def login(request):
    """
    Logs in a user account by creating a session token and setting it as a cookie.

    If "remember_me" is true, the session token will have a significantly longer (but not
    infinite) expiration time.
    """
    email = request.validated_data.get("email")
    password = request.validated_data.get("password")
    remember_me = request.validated_data.get("remember_me")

    # Check if the user is already logged in
    acct_token = request.COOKIES.get(ACCOUNT_COOKIE_NAME)
    if acct_token:
        try:
            with transaction.atomic():
                session = get_session(acct_token)
                if not session:
                    raise UserSession.DoesNotExist
                session.save()  # To update last_used to now

            # At this point the account is authenticated
            logger.info("User %s is already logged in.", session.user_account.email)
            response = Response(
                {"error": {"general": ["You are already logged in."]}}, status=400
            )
            # Refresh the session token cookie
            response.set_cookie(
                key=ACCOUNT_COOKIE_NAME,
                value=acct_token,
                httponly=True,
                secure=True,
                samesite="Lax",
                max_age=(
                    LONG_SESS_EXP_SECONDS if session.is_extended else SESS_EXP_SECONDS
                ),
            )
            return response
        except UserSession.DoesNotExist:
            logger.info("Account session expired.")
        except DatabaseError as e:
            logger.db_error(e)
            return GENERIC_ERR_RESPONSE
        except Exception as e:
            logger.error(e)
            return GENERIC_ERR_RESPONSE

    BAD_AUTH_RESPONSE = Response(
        {"error": {"general": ["Email or password is incorrect."]}}, status=400
    )  # To ensure consistency

    try:
        user = UserAccount.objects.get(email=email)
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            logger.info("Login failed for %s: Incorrect password.", email)
            return BAD_AUTH_RESPONSE

        session_token = str(uuid.uuid4())
        with transaction.atomic():
            UserSession.objects.create(
                session_token=session_token, user_account=user, is_extended=remember_me
            )
            UserLogin.objects.create(user_account=user)
        logger.debug("Session token for %s: %s", email, session_token)

    except UserAccount.DoesNotExist:
        logger.info("Login failed for %s: User does not exist.", email)
        return BAD_AUTH_RESPONSE
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    response = Response({"message": ["Login successful."]}, status=200)
    response.set_cookie(
        key=ACCOUNT_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=LONG_SESS_EXP_SECONDS if remember_me else SESS_EXP_SECONDS,
    )
    return response


@api_endpoint("POST")
@validate_json_input(PasswordSerializer)
@validate_output(MessageOutputSerializer)
def check_password(request):
    """
    Checks if the provided password meets the security criteria.

    Returns a list of issues with the password if invalid.
    """
    password = request.validated_data.get("password")

    if errors := validate_password(password):
        return Response({"error": {"password": errors}}, status=400)

    return Response({"message": ["Password is valid."]})


@api_endpoint("GET")
@require_account_auth
@validate_output(MessageOutputSerializer)
def check_account_auth(request):
    """
    Checks if the client is authenticated with a user account.

    In the future, this endpoint could be used to return user-personalized data like
    settings or preferences.
    """
    return Response({"message": [f"Logged in as {request.user.email}."]}, status=200)


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


@api_endpoint("POST")
@rate_limit(
    PasswordResetThrottle,
    "Password reset limit reached ({rate}). Try again later.",
)
@validate_json_input(EmailSerializer)
@validate_output(MessageOutputSerializer)
def start_password_reset(request):
    """
    Starts the password reset process by sending a password reset link to the specified
    email.

    If the email address is not associated with a user account, nothing will happen.

    To resend the email, this endpoint can be called again with the same input. A new
    reset token will be generated and the old one invalidated.
    """
    email = request.validated_data.get("email")

    try:
        user = UserAccount.objects.get(email=email)
        reset_token = str(uuid.uuid4())
        with transaction.atomic():
            PasswordResetToken.objects.filter(user_account=user).delete()
            PasswordResetToken.objects.create(
                reset_token=reset_token, user_account=user
            )
        logger.debug("Password reset token for %s: %s", email, reset_token)

        if SEND_EMAILS:
            send_mail(
                subject="Plancake - Reset Password",
                message=f"Click this link to reset your password:\n{BASE_URL}/reset-password?token={reset_token}\n\nNot you? Nothing to worry about, just ignore this email.",
                from_email=None,  # Use the default from settings
                recipient_list=[email],
                fail_silently=False,
            )

    except UserAccount.DoesNotExist:
        logger.info("Password reset failed for %s: User does not exist.", email)
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response(
        {
            "message": [
                "An email has been sent to your address with password reset instructions."
            ]
        },
        status=200,
    )


@api_endpoint("POST")
@validate_json_input(PasswordResetSerializer)
@validate_output(MessageOutputSerializer)
def reset_password(request):
    """
    Resets the password for a user account given a valid password reset token.

    Also removes all currently active sessions as a security measure. This means that you
    probably shouldn't call this endpoint while the user is currently logged in.
    """
    reset_token = request.validated_data.get("reset_token")
    new_password = request.validated_data.get("new_password")

    if errors := validate_password(new_password):
        logger.info("Password reset failed: Invalid new password.")
        return Response({"error": {"new_password": errors}}, status=400)

    try:
        with transaction.atomic():
            reset_token_obj = PasswordResetToken.objects.get(
                reset_token=reset_token,
                created_at__gte=datetime.now()
                - timedelta(seconds=PWD_RESET_EXP_SECONDS),
            )
            user = reset_token_obj.user_account

            # Check if the new password is actually new
            if bcrypt.checkpw(new_password.encode(), user.password_hash.encode()):
                logger.info("Password reset failed: New password was not new.")
                return Response(
                    {
                        "error": {
                            "new_password": [
                                "New password must be different from old password."
                            ]
                        }
                    },
                    status=400,
                )

            user.password_hash = bcrypt.hashpw(
                new_password.encode(), bcrypt.gensalt()
            ).decode()
            user.save()
            reset_token_obj.delete()  # Make sure to remove the reset token after use

            # Remove all active sessions for the user
            UserSession.objects.filter(user_account=user).delete()

    except PasswordResetToken.DoesNotExist:
        logger.info("Password reset failed: Invalid reset token.")
        return Response(
            {"error": {"reset_token": ["Invalid reset token."]}}, status=404
        )
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    return Response({"message": ["Password reset successfully."]}, status=200)


@api_endpoint("POST")
@validate_output(MessageOutputSerializer)
def logout(request):
    """
    Logs out the currently-authenticated user account by deleting the session token in the
    database and the cookie on the client.
    """
    try:
        if token := request.COOKIES.get(ACCOUNT_COOKIE_NAME):
            UserSession.objects.filter(session_token=token).delete()
        else:
            logger.info("User already logged out.")
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    response = Response({"message": ["Logged out successfully."]}, status=200)
    response.delete_cookie(ACCOUNT_COOKIE_NAME)
    return response


@api_endpoint("POST")
@require_account_auth
@validate_json_input(PasswordSerializer)
@validate_output(MessageOutputSerializer)
def delete_account(request):
    """
    Deletes the currently-authenticated user account after verifying the password.
    """
    password = request.validated_data.get("password")
    user = request.user

    if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        logger.info("Account deletion failed for %s: Incorrect password.", user.email)
        return Response({"error": {"password": ["Incorrect password."]}}, status=400)
    try:
        user.delete()
    except DatabaseError as e:
        logger.db_error(e)
        return GENERIC_ERR_RESPONSE
    except Exception as e:
        logger.error(e)
        return GENERIC_ERR_RESPONSE

    response = Response({"message": ["Account deleted successfully."]}, status=200)
    response.delete_cookie(ACCOUNT_COOKIE_NAME)
    return response
