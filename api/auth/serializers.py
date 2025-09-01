from rest_framework import serializers


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(required=True)


class RegisterAccountSerializer(EmailSerializer, PasswordSerializer):
    pass


class EmailVerifySerializer(serializers.Serializer):
    verification_code = serializers.CharField(required=True)


class LoginSerializer(RegisterAccountSerializer):
    remember_me = serializers.BooleanField(default=False, required=False)


class PasswordResetSerializer(serializers.Serializer):
    reset_token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
