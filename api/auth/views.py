from rest_framework.decorators import api_view
from rest_framework import serializers
from rest_framework.response import Response

from django.db import transaction

from datetime import datetime, timedelta

from api.settings import SESS_EXP_SECONDS, EMAIL_CODE_EXP_SECONDS
from api.models import UserAccount, UnverifiedUserAccount, UserSession
from api.utils import validate_input
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
            {"message": ["An email has been sent to your address for verification"]},
            status=200,
        )

    except Exception as e:
        print(e)
        return Response(
            {"error": {"general": ["An unknown error has occurred"]}}, status=500
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
            UserAccount.objects.create(
                email=unverified_user.email,
                password_hash=unverified_user.password_hash,
                is_guest=False,
            )
            # Delete the unverified user account
            unverified_user.delete()

    except UnverifiedUserAccount.DoesNotExist:
        return Response(
            {"error": {"ver_code": ["Invalid verification code"]}}, status=404
        )
    except Exception as e:
        print(e)
        return Response(
            {"error": {"general": ["An unknown error has occurred"]}}, status=500
        )

    return Response({"message": ["Email verified successfully"]}, status=200)


@api_view(["POST"])
@validate_input(AccountInfoSerializer)
def login(request):
    email = request.validated_data.get("email")
    password = request.validated_data.get("password")

    INCORRECT_AUTH_MSG = "Email or password is incorrect"  # To ensure consistency

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
            {"error": {"general": ["An unknown error has occurred"]}}, status=500
        )

    response = Response({"message": ["Login successful"]})
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

    return Response({"message": ["Password is valid"]})
