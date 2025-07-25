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


class PasswordResetToken(models.Model):
    reset_token = models.CharField(max_length=255, primary_key=True)
    user_account = models.ForeignKey(
        UserAccount, on_delete=models.CASCADE, related_name="password_reset_tokens"
    )
    created_at = DateTimeNoTZField(auto_now_add=True)


class UserLogin(models.Model):
    user_login_id = models.AutoField(primary_key=True)
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


class EventParticipant(models.Model):
    event_participant_id = models.AutoField(primary_key=True)
    user_event = models.ForeignKey(
        UserEvent, on_delete=models.CASCADE, related_name="participants"
    )
    user_account = models.ForeignKey(
        UserAccount, on_delete=models.CASCADE, related_name="events_participated"
    )
    display_name = models.CharField(max_length=25, null=True)
    time_zone = models.CharField(max_length=50, null=True)


class EventWeekdayTimeslot(models.Model):
    event_weekday_timeslot_id = models.AutoField(primary_key=True)
    user_event = models.ForeignKey(
        UserEvent, on_delete=models.CASCADE, related_name="weekday_timeslots"
    )
    weekday = models.PositiveSmallIntegerField()
    timeslot = models.TimeField()


class EventDateTimeslot(models.Model):
    event_date_timeslot_id = models.AutoField(primary_key=True)
    user_event = models.ForeignKey(
        UserEvent, on_delete=models.CASCADE, related_name="date_timeslots"
    )
    timeslot = DateTimeNoTZField()


class EventWeekdayAvailability(models.Model):
    event_weekday_availability_id = models.AutoField(primary_key=True)
    event_participant = models.ForeignKey(
        EventParticipant,
        on_delete=models.CASCADE,
        related_name="event_weekday_availabilities",
    )
    event_weekday_timeslot = models.ForeignKey(
        EventWeekdayTimeslot,
        on_delete=models.CASCADE,
        related_name="participant_availabilities",
    )
    is_available = models.BooleanField()


class EventDateAvailability(models.Model):
    event_date_availability_id = models.AutoField(primary_key=True)
    event_participant = models.ForeignKey(
        EventParticipant,
        on_delete=models.CASCADE,
        related_name="event_date_availabilities",
    )
    event_date_timeslot = models.ForeignKey(
        EventDateTimeslot,
        on_delete=models.CASCADE,
        related_name="participant_availabilities",
    )
    is_available = models.BooleanField()
