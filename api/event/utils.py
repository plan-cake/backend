import random
import re
import string
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Prefetch

from api.models import EventDateTimeslot, EventWeekdayTimeslot, UrlCode, UserEvent
from api.settings import (
    MAX_EVENT_DAYS,
    RAND_URL_CODE_ATTEMPTS,
    RAND_URL_CODE_LENGTH,
    URL_CODE_EXP_SECONDS,
)


def check_code_available(code):
    try:
        existing_code = UrlCode.objects.get(url_code=code)
        if existing_code.last_used >= datetime.now() - timedelta(
            seconds=URL_CODE_EXP_SECONDS
        ):
            return False
    except UrlCode.DoesNotExist:
        pass

    return True


def check_custom_code(code):
    if len(code) > 255:
        return "Code must be 255 characters or less."
    if not re.fullmatch(r"[A-Za-z0-9\-]+", code):
        return "Code must contain only alphanumeric characters and dashes."

    RESERVED_KEYWORDS = [
        "api",
        "dashboard",
        "forgot-password",
        "login",
        "new-event",
        "reset-password",
        "register",
        "verify-email",
    ]
    if code in RESERVED_KEYWORDS or not check_code_available(code):
        return "Code unavailable."


def generate_code():
    def generate_random_string():
        return "".join(
            # Using SystemRandom() is "cryptographically more secure"
            random.SystemRandom().choices(
                string.ascii_letters + string.digits, k=RAND_URL_CODE_LENGTH
            )
        )

    code = generate_random_string()
    for _ in range(RAND_URL_CODE_ATTEMPTS):
        if check_code_available(code):
            return code
        code = generate_random_string()
    raise Exception("Failed to generate a unique URL code.")


def check_timeslot_times(timeslots):
    for timeslot in timeslots:
        if timeslot.minute % 15 != 0:
            return False
    return True


def validate_date_timeslots(
    timeslots: list[datetime],
    earliest_date_local: datetime.date,
    user_time_zone: str,
    editing: bool = False,
):
    """
    Validates timeslots for a date event.

    The editing parameter determines the error message given if start_date is too early.
    """
    start_date = min(ts.date() for ts in timeslots)
    end_date = max(ts.date() for ts in timeslots)

    start_date_local = min(timeslots).astimezone(ZoneInfo(user_time_zone)).date()

    errors = {}
    if start_date_local < earliest_date_local:
        if editing:
            errors["timeslots"] = [
                "Event cannot start earlier than today, or be moved earlier if already before today."
            ]
        else:
            errors["timeslots"] = ["Event must start today or in the future."]
    if (end_date - start_date).days > MAX_EVENT_DAYS:
        errors["timeslots"] = [f"Max event length is {MAX_EVENT_DAYS} days."]

    if not check_timeslot_times(timeslots):
        errors["timeslots"] = ["Timeslots must be on 15-minute intervals."]

    return errors


def validate_weekday_timeslots(timeslots):
    if not check_timeslot_times(timeslots):
        return {"timeslots": ["Timeslots must be on 15-minute intervals."]}
    return {}


def get_event_type(date_type):
    match date_type:
        case UserEvent.EventType.SPECIFIC:
            return "Date"
        case UserEvent.EventType.GENERIC:
            return "Week"


def event_lookup(event_code: str):
    """
    Looks up an event by its URL code.

    Also prefetches related timeslot data for efficiency.
    """
    return UserEvent.objects.prefetch_related(
        Prefetch(
            "date_timeslots", queryset=EventDateTimeslot.objects.order_by("timeslot")
        ),
        Prefetch(
            "weekday_timeslots",
            queryset=EventWeekdayTimeslot.objects.order_by("weekday", "timeslot"),
        ),
    ).get(url_code=event_code)


def format_event_info(
    event: UserEvent,
):
    """
    Formats event info into a dictionary to satisfy the output serializers on certain
    endpoints.

    For query efficiency, the event's timeslots should be prefetched.
    """
    start_date = None
    end_date = None
    start_weekday = None
    end_weekday = None
    event_type = ""
    start_hour = -1
    end_hour = -1

    event_type = get_event_type(event.date_type)
    first_timeslot = None
    last_timeslot = None
    match event_type:
        case "Date":
            all_timeslots = list(event.date_timeslots.all())
            first_timeslot = all_timeslots[0]
            last_timeslot = all_timeslots[-1]
            start_date = first_timeslot.timeslot.date()
            end_date = last_timeslot.timeslot.date()
        case "Week":
            all_timeslots = list(event.weekday_timeslots.all())
            first_timeslot = all_timeslots[0]
            last_timeslot = all_timeslots[-1]
            start_weekday = first_timeslot.weekday
            end_weekday = last_timeslot.weekday

    start_hour = first_timeslot.timeslot.hour
    # The last timeslot will always be XX:45, so just add 1 to the hour
    end_hour = last_timeslot.timeslot.hour + 1

    data = {
        "title": event.title,
        "event_type": event_type,
        "start_hour": start_hour,
        "end_hour": end_hour,
        "time_zone": event.time_zone,
    }
    # Add the extra fields only if not null, otherwise the serializer complains
    if event.duration:
        data["duration"] = event.duration
    if start_date:
        data["start_date"] = start_date
    if end_date:
        data["end_date"] = end_date
    if start_weekday is not None:
        data["start_weekday"] = start_weekday
    if end_weekday is not None:
        data["end_weekday"] = end_weekday

    return data


def js_weekday(weekday: int) -> int:
    """
    Converts a Python weekday (0 = Monday) to a JavaScript weekday (0 = Sunday).
    """
    return (weekday + 1) % 7
