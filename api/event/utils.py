import re
from datetime import datetime, timedelta

from api.models import UrlCode
from api.settings import URL_CODE_EXP_SECONDS


def check_code_available(code):
    try:
        existing_code = UrlCode.objects.get(url_code=code)
        if existing_code.last_used < datetime.now() - timedelta(
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
