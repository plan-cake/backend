from rest_framework.decorators import api_view
from rest_framework import serializers
from rest_framework.response import Response

from django.db import transaction

from .models import UserAccount, UserSession
from .utils import validate_password

import bcrypt
import uuid


# Create your views here.
def index(request):
    return Response("Hello, world!")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True)


@api_view(["POST"])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"error": serializer.errors}, status=400)
    email = serializer.validated_data.get("email")
    password = serializer.validated_data.get("password")
    if errors := validate_password(password):
        return Response({"error": {"password": errors}}, status=400)

    # Hash the password before saving
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # Create a session token for the new user
    session_token = str(uuid.uuid4())
    try:
        # Check if the email already exists
        if UserAccount.objects.filter(email=email).exists():
            return Response(
                {"error": {"email": ["An account with this email already exists"]}},
                status=400,
            )

        with transaction.atomic():
            new_user = UserAccount.objects.create(
                email=email, password_hash=pwd_hash, is_guest=False
            )
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
        max_age=2592000,  # 30 days
    )
    return response
