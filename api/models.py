from django.db import models


class DateTimeNoTZField(models.DateTimeField):
    """
    Custom DateTimeField without time zones
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return "TIMESTAMP WITHOUT TIME ZONE"
        return super().db_type(connection)


class UserAccount(models.Model):
    user_account_id = models.AutoField(primary_key=True)
    email = models.EmailField(unique=True, null=True)
    password_hash = models.CharField(max_length=255, null=True)
    display_name = models.CharField(max_length=25, null=True)
    is_internal = models.BooleanField(default=False)
    is_guest = models.BooleanField()
    created_at = DateTimeNoTZField(auto_now_add=True)
    updated_at = DateTimeNoTZField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["email"])]


class UserSession(models.Model):
    session_token = models.CharField(max_length=255, primary_key=True)
    user_account = models.ForeignKey(
        UserAccount, on_delete=models.CASCADE, related_name="session_tokens"
    )
    last_used = DateTimeNoTZField(auto_now=True)


class UserLogin(models.Model):
    pk = models.CompositePrimaryKey("user_account", "login_time")
    user_account = models.ForeignKey(
        UserAccount, on_delete=models.CASCADE, related_name="logins"
    )
    login_time = DateTimeNoTZField(auto_now_add=True)


class UserEvent(models.Model):
    user_event_id = models.AutoField(primary_key=True)
    user_account = models.ForeignKey(
        UserAccount, on_delete=models.CASCADE, related_name="events"
    )
    title = models.CharField(max_length=50)

    class EventType(models.TextChoices):
        GENERIC = "GENERIC", "Generic"
        SPECIFIC = "SPECIFIC", "Specific"

    date_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
    )
    duration = models.PositiveSmallIntegerField(null=True)
    created_at = DateTimeNoTZField(auto_now_add=True)
    updated_at = DateTimeNoTZField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user_account"])]


class UrlCode(models.Model):
    url_code = models.CharField(max_length=255, primary_key=True)
    user_event = models.ForeignKey(
        UserEvent, on_delete=models.CASCADE, related_name="url_codes"
    )
    last_used = DateTimeNoTZField(auto_now=True)
