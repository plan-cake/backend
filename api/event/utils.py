import random
import re
import string
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from api.models import UrlCode
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

    RESERVED_KEYWORDS = []  # TODO: Add this later after consulting with frontend
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


def daterange(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def timerange(start_hour, end_hour):
    start_time = time(start_hour)
    end_time = time(end_hour) if end_hour != 24 else time(23, 59)
    # Adding the date is a workaround since you can't use timedelta with just times
    date = datetime.today()
    current = datetime.combine(date, start_time)
    end_dt = datetime.combine(date, end_time)
    while current < end_dt:
        yield current.time()
        current += timedelta(minutes=15)


def validate_date_input(
    start_date, end_date, start_hour, end_hour, earliest_date, editing=False
):
    """
    Validates date and time ranges for an event.

    The editing parameter determines the error message given if start_date is too early.
    """
    errors = {}
    if start_date < earliest_date:
        if editing:
            errors["start_date"] = [
                "Start date cannot be set earlier than today, or moved earlier if already before today."
            ]
        else:
            errors["start_date"] = ["Start date must be today or in the future."]
    if start_date > end_date:
        errors["end_date"] = ["End date must be on or after start date."]
    if start_hour >= end_hour:
        errors["end_hour"] = ["End hour must be after start hour."]
    if (end_date - start_date).days > MAX_EVENT_DAYS:
        errors["end_date"] = [
            f"End date must be within {MAX_EVENT_DAYS} days of start date."
        ]

    return errors


def validate_weekday_input(start_weekday, end_weekday, start_hour, end_hour):
    errors = {}
    if start_weekday > end_weekday:
        errors["end_weekday"] = ["End weekday must be on or after start weekday."]
    if start_hour >= end_hour:
        errors["end_hour"] = ["End hour must be after start hour."]
    return errors
