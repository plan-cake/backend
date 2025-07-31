from rest_framework.decorators import api_view
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from django.db import transaction
from django.core.mail import send_mail

from datetime import datetime, timedelta

from api.settings import (
    SESS_EXP_SECONDS,
    LONG_SESS_EXP_SECONDS,
    EMAIL_CODE_EXP_SECONDS,
    PWD_RESET_EXP_SECONDS,
    GENERIC_ERR_RESPONSE,
    BASE_URL,
)
from api.models import (
    UserAccount,
    UnverifiedUserAccount,
    UserSession,
    PasswordResetToken,
    UserLogin,
)
from api.utils import validate_json_input, require_account_auth, rate_limit
from api.auth.utils import validate_password

import bcrypt
import uuid


class RegisterAccountSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)


class RegisterAccountThrottle(AnonRateThrottle):
    scope = "user_account_creation"


@api_view(["POST"])
@rate_limit(
    RegisterAccountThrottle, "Account creation limit reached ({rate}). Try again later."
)
@validate_json_input(RegisterAccountSerializer)
def register(request):
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
            send_mail(
                subject="Plancake - Email in Use",
                message=f"Looks like your email was already used for a Plancake account.\n\nNot you? Nothing to worry about, just ignore this email.",
                from_email=None,  # Use the default from settings
                recipient_list=[email],
                fail_silently=False,
            )
            pass
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

    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE


class EmailVerifySerializer(serializers.Serializer):
    verification_code = serializers.CharField(required=True)


@api_view(["POST"])
@validate_json_input(EmailVerifySerializer)
def verify_email(request):
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


@api_view(["POST"])
@rate_limit(LoginThrottle, "Login limit reached ({rate}). Try again later.")
@validate_json_input(LoginSerializer)
def login(request):
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


@api_view(["POST"])
@validate_json_input(PasswordSerializer)
def check_password(request):
    password = request.validated_data.get("password")

    if errors := validate_password(password):
        return Response({"error": {"password": errors}}, status=400)

    return Response({"message": ["Password is valid."]})


@api_view(["GET"])
@require_account_auth
def check_account_auth(request):
    """
    Endpoint to check if the user is authenticated.

    In the future, this could also return data like settings and personalization.
    """
    return Response({"message": [f"Logged in as {request.user.email}."]}, status=200)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


@api_view(["POST"])
@validate_json_input(EmailSerializer)
def start_password_reset(request):
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
        send_mail(
            subject="Plancake - Reset Password",
            message=f"Click this link to reset your password:\n{BASE_URL}/reset-password?token={reset_token}\n\nNot you? Nothing to worry about, just ignore this email.",
            from_email=None,  # Use the default from settings
            recipient_list=[email],
            fail_silently=False,
        )
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


@api_view(["POST"])
@validate_json_input(PasswordResetSerializer)
def reset_password(request):
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

    except PasswordResetToken.DoesNotExist:
        return Response(
            {"error": {"reset_token": ["Invalid reset token."]}}, status=404
        )
    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE

    return Response({"message": ["Password reset successfully."]}, status=200)


@api_view(["POST"])
def logout(request):
    try:
        if token := request.COOKIES.get("account_sess_token"):
            UserSession.objects.filter(session_token=token).delete()
    except Exception as e:
        print(e)
        return GENERIC_ERR_RESPONSE

    response = Response({"message": ["Logged out successfully."]}, status=200)
    response.delete_cookie("account_sess_token")
    return response


@api_view(["POST"])
@require_account_auth
@validate_json_input(PasswordSerializer)
def delete_account(request):
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
