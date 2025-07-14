from rest_framework.decorators import api_view
from rest_framework import serializers
from rest_framework.response import Response

from django.db import transaction

from api.settings import SESS_EXP_SECONDS
from .models import UserAccount, UserSession
from .utils import validate_password

import bcrypt
import uuid


# Create your views here.
def index(request):
    return Response("Hello, world!")


class AccountInfoSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)


@api_view(["POST"])
def register(request):
    serializer = AccountInfoSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=400)
    email = serializer.validated_data.get("email")
    password = serializer.validated_data.get("password")

    try:
        # Check if the email already exists
        if UserAccount.objects.filter(email=email).exists():
            return Response(
                {"error": {"email": ["An account with this email already exists"]}},
                status=400,
            )

        # Then validate the password after
        if errors := validate_password(password):
            return Response({"error": {"password": errors}}, status=400)
        pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Now start a transaction to make sure both database calls are successful
        with transaction.atomic():
            new_user = UserAccount.objects.create(
                email=email, password_hash=pwd_hash, is_guest=False
            )

            session_token = str(uuid.uuid4())
            UserSession.objects.create(
                session_token=session_token, user_account=new_user
            )

    except Exception as e:
        print(e)
        return Response(
            {"error": {"general": ["An unknown error has occurred"]}}, status=500
        )

    response = Response({"message": ["Registration successful"]})
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
def login(request):
    serializer = AccountInfoSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=400)
    email = serializer.validated_data.get("email")
    password = serializer.validated_data.get("password")

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
