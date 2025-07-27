from rest_framework.decorators import api_view
from rest_framework import serializers
from rest_framework.response import Response

from django.db import transaction

from datetime import datetime, timedelta

from api.settings import SESS_EXP_SECONDS, EMAIL_CODE_EXP_SECONDS, PWD_RESET_EXP_SECONDS
from api.models import (
    UserAccount,
    UnverifiedUserAccount,
    UserSession,
    PasswordResetToken,
)
from api.utils import validate_input, require_auth
from api.auth.utils import validate_password

import bcrypt
import uuid


class AccountInfoSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)


@api_view(["POST"])
@validate_input(AccountInfoSerializer)
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
            # TODO: send an email to the user to say the email is already registered
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
                # TODO: send an email to the user with the verification link

        return Response(
            {"message": ["An email has been sent to your address for verification."]},
            status=200,
        )

    except Exception as e:
        print(e)
        return Response(
            {"error": {"general": ["An unknown error has occurred."]}}, status=500
        )


class EmailVerifySerializer(serializers.Serializer):
    verification_code = serializers.CharField(required=True)


@api_view(["POST"])
@validate_input(EmailVerifySerializer)
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
            # Automatically log in the user
            session_token = str(uuid.uuid4())
            UserSession.objects.create(
                session_token=session_token, user_account=new_user
            )

    except UnverifiedUserAccount.DoesNotExist:
        return Response(
            {"error": {"verification_code": ["Invalid verification code."]}}, status=404
        )
    except Exception as e:
        print(e)
        return Response(
            {"error": {"general": ["An unknown error has occurred."]}}, status=500
        )

    response = Response({"message": ["Email verified successfully."]}, status=200)
    response.set_cookie(
        key="account_sess_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=SESS_EXP_SECONDS,
    )
    return response


@api_view(["POST"])
@validate_input(AccountInfoSerializer)
def login(request):
    email = request.validated_data.get("email")
    password = request.validated_data.get("password")

    INCORRECT_AUTH_MSG = "Email or password is incorrect."  # To ensure consistency

    try:
        user = UserAccount.objects.get(email=email)
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return Response({"error": {"general": [INCORRECT_AUTH_MSG]}}, status=400)

        session_token = str(uuid.uuid4())
        UserSession.objects.create(session_token=session_token, user_account=user)

    except UserAccount.DoesNotExist:
        return Response({"error": {"general": [INCORRECT_AUTH_MSG]}}, status=404)
    except Exception as e:
        print(e)
        return Response(
            {"error": {"general": ["An unknown error has occurred."]}}, status=500
        )

    response = Response({"message": ["Login successful."]}, status=200)
    response.set_cookie(
        key="account_sess_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=SESS_EXP_SECONDS,
    )
    return response


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(required=True)


@api_view(["POST"])
@validate_input(PasswordSerializer)
def check_password(request):
    password = request.validated_data.get("password")

    if errors := validate_password(password):
        return Response({"error": {"password": errors}}, status=400)

    return Response({"message": ["Password is valid."]})


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


@api_view(["POST"])
@validate_input(EmailSerializer)
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
        # TODO: Send the email to the user
    except UserAccount.DoesNotExist:
        pass  # Do not reveal if the email exists or not
    except Exception as e:
        print(e)
        return Response(
            {"error": {"general": ["An unknown error has occurred."]}}, status=500
        )

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
@validate_input(PasswordResetSerializer)
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
        return Response(
            {"error": {"general": ["An unknown error has occurred."]}}, status=500
        )

    return Response({"message": ["Password reset successfully."]}, status=200)


@api_view(["POST"])
@require_auth
def logout(request):
    try:
        # Guaranteed to exist because of the decorator
        token = request.COOKIES.get("account_sess_token")
        UserSession.objects.filter(session_token=token).delete()
    except Exception as e:
        print(e)
        return Response(
            {"error": {"general": ["An unknown error has occurred."]}}, status=500
        )

    response = Response({"message": ["Logged out successfully."]}, status=200)
    response.delete_cookie("account_sess_token")
    return response
