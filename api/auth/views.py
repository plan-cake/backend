import uuid
from datetime import datetime, timedelta

import bcrypt
from django.core.mail import send_mail
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from api.auth.utils import validate_password
from api.models import (
    PasswordResetToken,
    UnverifiedUserAccount,
    UserAccount,
    UserLogin,
    UserSession,
)
from api.settings import (
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
    rate_limit,
    require_account_auth,
    validate_json_input,
    validate_output,
)


class RegisterAccountSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)


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
        # Remove expired verification codes
        UnverifiedUserAccount.objects.filter(
            created_at__lt=datetime.now() - timedelta(seconds=EMAIL_CODE_EXP_SECONDS)
        ).delete()

        # Validate the password first
        if errors := validate_password(password):
            return Response({"error": {"password": errors}}, status=400)
        pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Check if the email already exists
        if UserAccount.objects.filter(email=email).exists():
            if SEND_EMAILS:
                send_mail(
                    subject="Plancake - Email in Use",
                    message=f"Looks like your email was already used for a Plancake account.\n\nNot you? Nothing to worry about, just ignore this email.",
                    from_email=None,  # Use the default from settings
                    recipient_list=[email],
                    fail_silently=False,
                )
            else:
                # Just print a message
                print(f"Email {email} in use!")
        else:
            # Create an unverified user account
            ver_code = str(uuid.uuid4())
            if UnverifiedUserAccount.objects.filter(email=email).exists():
                # If the email was already used, update the verification code
                UnverifiedUserAccount.objects.filter(email=email).update(
                    verification_code=ver_code, created_at=datetime.now()
                )
            else:
                UnverifiedUserAccount.objects.create(
                    verification_code=ver_code,
                    email=email,
                    password_hash=pwd_hash,
                )

            if SEND_EMAILS:
                send_mail(
                    subject="Plancake - Email Verification",
                    message=f"Welcome to Plancake!\n\nClick this link to verify your email:\n{BASE_URL}/verify-email?code={ver_code}\n\nNot you? Nothing to worry about, just ignore this email.",
                    from_email=None,  # Use the default from settings
                    recipient_list=[email],
                    fail_silently=False,
                )
            else:
                # Just print the code
                print(f"{email} registered as unverified with code: {ver_code}")

        return Response(
            {"message": ["An email has been sent to your address for verification."]},
            status=200,
        )

    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


@api_endpoint("POST")
@validate_json_input(EmailSerializer)
@validate_output(MessageOutputSerializer)
def resend_register_email(request):
    """
    Attempts to resend the verification email for an unverified user account.

    If the email address is either already used for a verified user account, or not
    associated with an unverified user account, nothing will happen.
    """
    email = request.validated_data.get("email")

    try:
        # Remove expired verification codes
        UnverifiedUserAccount.objects.filter(
            created_at__lt=datetime.now() - timedelta(seconds=EMAIL_CODE_EXP_SECONDS)
        ).delete()
        unverified_user = UnverifiedUserAccount.objects.get(email=email)
        if SEND_EMAILS:
            send_mail(
                subject="Plancake - Email Verification",
                message=f"Welcome to Plancake!\n\nClick this link to verify your email:\n{BASE_URL}/verify-email?code={unverified_user.verification_code}\n\nNot you? Nothing to worry about, just ignore this email.",
                from_email=None,  # Use the default from settings
                recipient_list=[email],
                fail_silently=False,
            )
        else:
            # Just print the verification code
            print(f"Verification code for {email}: {unverified_user.verification_code}")

    except UnverifiedUserAccount.DoesNotExist:
        pass  # Do not reveal if the email exists or not
    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE

    return Response({"message": ["Verification email resent."]}, status=200)


class EmailVerifySerializer(serializers.Serializer):
    verification_code = serializers.CharField(required=True)


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
        # Remove expired verification codes
        UnverifiedUserAccount.objects.filter(
            created_at__lt=datetime.now() - timedelta(seconds=EMAIL_CODE_EXP_SECONDS)
        ).delete()

        unverified_user = UnverifiedUserAccount.objects.get(verification_code=ver_code)
        with transaction.atomic():
            # Create the user account
            new_user = UserAccount.objects.create(
                email=unverified_user.email,
                password_hash=unverified_user.password_hash,
                is_guest=False,
            )
            # Delete the unverified user account
            unverified_user.delete()

    except UnverifiedUserAccount.DoesNotExist:
        return Response(
            {"error": {"verification_code": ["Invalid verification code."]}}, status=404
        )
    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE

    return Response({"message": ["Email verified successfully."]}, status=200)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)
    remember_me = serializers.BooleanField(default=False, required=False)


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

    BAD_AUTH_RESPONSE = Response(
        {"error": {"general": ["Email or password is incorrect."]}}, status=400
    )  # To ensure consistency

    try:
        user = UserAccount.objects.get(email=email)
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return BAD_AUTH_RESPONSE

        session_token = str(uuid.uuid4())
        with transaction.atomic():
            UserSession.objects.create(
                session_token=session_token, user_account=user, is_extended=remember_me
            )
            UserLogin.objects.create(user_account=user)

    except UserAccount.DoesNotExist:
        return BAD_AUTH_RESPONSE
    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE

    response = Response({"message": ["Login successful."]}, status=200)
    response.set_cookie(
        key="account_sess_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=LONG_SESS_EXP_SECONDS if remember_me else SESS_EXP_SECONDS,
    )
    return response


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(required=True)


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


@api_endpoint("POST")
@validate_json_input(EmailSerializer)
@validate_output(MessageOutputSerializer)
def start_password_reset(request):
    """
    Starts the password reset process by sending a password reset link to the specified
    email.

    If the email address is not associated with a user account, nothing will happen.
    """
    email = request.validated_data.get("email")
    try:
        # Remove expired password reset tokens
        PasswordResetToken.objects.filter(
            created_at__lt=datetime.now() - timedelta(seconds=PWD_RESET_EXP_SECONDS)
        ).delete()

        user = UserAccount.objects.get(email=email)
        reset_token = str(uuid.uuid4())
        if PasswordResetToken.objects.filter(user_account=user).exists():
            # If the user already has a reset token, update it
            PasswordResetToken.objects.filter(user_account=user).update(
                reset_token=reset_token, created_at=datetime.now()
            )
        else:
            # Create a new password reset token
            PasswordResetToken.objects.create(
                reset_token=reset_token, user_account=user
            )
        if SEND_EMAILS:
            send_mail(
                subject="Plancake - Reset Password",
                message=f"Click this link to reset your password:\n{BASE_URL}/reset-password?token={reset_token}\n\nNot you? Nothing to worry about, just ignore this email.",
                from_email=None,  # Use the default from settings
                recipient_list=[email],
                fail_silently=False,
            )
        else:
            # Just print the reset token
            print(f"Password reset token for {email}: {reset_token}")

    except UserAccount.DoesNotExist:
        pass  # Do not reveal if the email exists or not
    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE

    return Response(
        {
            "message": [
                "An email has been sent to your address with password reset instructions."
            ]
        },
        status=200,
    )


class PasswordResetSerializer(serializers.Serializer):
    reset_token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


@api_endpoint("POST")
@validate_json_input(PasswordResetSerializer)
@validate_output(MessageOutputSerializer)
def reset_password(request):
    """
    Resets the password for a user account given a valid password reset token.

    Also removes all currently active sessions as a security measure.
    """
    reset_token = request.validated_data.get("reset_token")
    new_password = request.validated_data.get("new_password")

    if errors := validate_password(new_password):
        return Response({"error": {"new_password": errors}}, status=400)

    try:
        # Remove expired password reset tokens
        PasswordResetToken.objects.filter(
            created_at__lt=datetime.now() - timedelta(seconds=PWD_RESET_EXP_SECONDS)
        ).delete()

        with transaction.atomic():
            reset_token_obj = PasswordResetToken.objects.get(reset_token=reset_token)
            user = reset_token_obj.user_account

            # Check if the new password is actually new
            if bcrypt.checkpw(new_password.encode(), user.password_hash.encode()):
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
        return Response(
            {"error": {"reset_token": ["Invalid reset token."]}}, status=404
        )
    except Exception as e:
        print(e)
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
        if token := request.COOKIES.get("account_sess_token"):
            UserSession.objects.filter(session_token=token).delete()
    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE

    response = Response({"message": ["Logged out successfully."]}, status=200)
    response.delete_cookie("account_sess_token")
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
        return Response({"error": {"password": ["Incorrect password."]}}, status=400)
    try:
        user.delete()
    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE

    response = Response({"message": ["Account deleted successfully."]}, status=200)
    response.delete_cookie("account_sess_token")
    return response
