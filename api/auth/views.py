from rest_framework.decorators import api_view
from rest_framework import serializers
from rest_framework.response import Response

from django.db import transaction

from api.settings import SESS_EXP_SECONDS
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
            if UnverifiedUserAccount.objects.filter(
                verification_code=ver_code
            ).exists():
                # In the astronomically low chance there's a UUID collision, return an error
                return Response(
                    {"error": {"general": ["An unknown error has occurred"]}},
                    status=500,
                )
            elif UnverifiedUserAccount.objects.filter(email=email).exists():
                # If the email was already used, update the verification code
                UnverifiedUserAccount.objects.filter(email=email).update(
                    verification_code=ver_code
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


@api_view(["POST"])
@validate_input(AccountInfoSerializer)
def login(request):
    email = request.validated_data.get("email")
    password = request.validated_data.get("password")

    try:
        user = UserAccount.objects.get(email=email)
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return Response({"error": {"password": ["Incorrect password"]}}, status=400)

        session_token = str(uuid.uuid4())
        UserSession.objects.create(session_token=session_token, user_account=user)

    except UserAccount.DoesNotExist:
        return Response(
            {"error": {"email": ["No account found with this email"]}}, status=404
        )
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
