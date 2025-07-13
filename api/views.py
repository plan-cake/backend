from rest_framework.decorators import api_view
from rest_framework import serializers
from rest_framework.response import Response

from .models import UserAccount
import bcrypt


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
    # Hash the password before saving
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        # Check if the email already exists
        if UserAccount.objects.filter(email=email).exists():
            return Response(
                {"error": "An account with this email already exists"}, status=400
            )
        UserAccount.objects.create(email=email, password_hash=pwd_hash, is_guest=False)
    except Exception as e:
        print(e)
        return Response({"error": "An unknown error has occurred"}, status=500)
    return Response({"message": f"Registration successful"})
