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


def validate_date_input(start_date, end_date, start_hour, end_hour, time_zone):
    errors = {}
    try:
        user_tz = ZoneInfo(time_zone)
        user_date = datetime.now(user_tz).date()
    except:
        errors["time_zone"] = ["Invalid time zone."]
        # Return early to avoid worse errors later
        return errors
    if start_date < user_date:
        # By comparing to the user's local date, we ensure that they don't get blocked
        # from creating an event just because they're behind UTC
        errors["start_date"] = ["start_date must be today or in the future."]
    if start_date > end_date:
        errors["end_date"] = ["end_date must be on or after start_date."]
    if start_hour >= end_hour:
        errors["end_hour"] = ["end_hour must be after start_hour."]
    if (end_date - start_date).days > MAX_EVENT_DAYS:
        errors["end_date"] = [
            f"end_date must be within {MAX_EVENT_DAYS} days of start_date."
        ]

    return errors
