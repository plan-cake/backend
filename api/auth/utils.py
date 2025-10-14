def validate_password(password):
    MIN_LENGTH = 8
    SPECIAL_CHARACTERS = """!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""

    LENGTH_CRIT = f"be at least {MIN_LENGTH} characters long"
    LOWER_CRIT = "contain at least one lowercase letter"
    UPPER_CRIT = "contain at least one uppercase letter"
    DIGIT_CRIT = "contain at least one digit"
    SPECIAL_CRIT = "contain at least one special character"

    is_strong = True
    criteria = {
        LENGTH_CRIT: True,
        LOWER_CRIT: True,
        UPPER_CRIT: True,
        DIGIT_CRIT: True,
        SPECIAL_CRIT: True,
    }
    if len(password) < MIN_LENGTH:
        criteria[LENGTH_CRIT] = False
        is_strong = False
    if not any(char.islower() for char in password):
        criteria[LOWER_CRIT] = False
        is_strong = False
    if not any(char.isupper() for char in password):
        criteria[UPPER_CRIT] = False
        is_strong = False
    if not any(char.isdigit() for char in password):
        criteria[DIGIT_CRIT] = False
        is_strong = False
    if not any(char in SPECIAL_CHARACTERS for char in password):
        criteria[SPECIAL_CRIT] = False
        is_strong = False

    return is_strong, criteria


def list_failed_criteria(criteria):
    return [f"Password must {crit}." for crit, passed in criteria.items() if not passed]
