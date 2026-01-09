import random
import re
import string
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Prefetch

from api.models import EventDateTimeslot, EventWeekdayTimeslot, UrlCode, UserEvent
from api.settings import MAX_EVENT_DAYS, RAND_URL_CODE_ATTEMPTS, RAND_URL_CODE_LENGTH


def check_code_available(code):
    try:
        UrlCode.objects.get(url_code=code)
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
        if (
            timeslot.minute % 15 != 0
            or timeslot.second != 0
            or timeslot.microsecond != 0
        ):
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
    if not timeslots:
        return {"timeslots": ["At least one timeslot is required."]}

    start_date = min(ts.date() for ts in timeslots)
    end_date = max(ts.date() for ts in timeslots)

    start_date_local = min(timeslots).astimezone(ZoneInfo(user_time_zone)).date()

    errors = {}

    def add_error(message):
        if "timeslots" not in errors:
            errors["timeslots"] = []
        errors["timeslots"].append(message)

    # The earliest date allowed is "today" in the user's local time zone, which is why
    # this uses a time zone conversion instead of UTC
    if start_date_local < earliest_date_local:
        if editing:
            add_error(
                "Event cannot start earlier than today, or be moved earlier if already before today."
            )
        else:
            add_error("Event must start today or in the future.")
    if (end_date - start_date).days > MAX_EVENT_DAYS:
        add_error(f"Max event length is {MAX_EVENT_DAYS} days.")

    if not check_timeslot_times(timeslots):
        add_error("Timeslots must be on 15-minute intervals.")

    return errors


def validate_weekday_timeslots(timeslots):
    if not timeslots:
        return {"timeslots": ["At least one timeslot is required."]}

    if not check_timeslot_times(timeslots):
        return {"timeslots": ["Timeslots must be on 15-minute intervals."]}
    return {}


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


def js_weekday(weekday: int) -> int:
    """
    Converts a Python weekday (0 = Monday) to a JavaScript weekday (0 = Sunday).
    """
    return (weekday + 1) % 7
