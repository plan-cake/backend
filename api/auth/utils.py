def validate_password(password):
    MIN_LENGTH = 8
    SPECIAL_CHARACTERS = """!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""

    errors = []
    if len(password) < MIN_LENGTH:
        errors.append(f"Password must be at least {MIN_LENGTH} characters long.")
    if not any(char.isdigit() for char in password):
        errors.append("Password must contain at least one digit.")
    if not any(char.isupper() for char in password):
        errors.append("Password must contain at least one uppercase letter.")
    if not any(char.islower() for char in password):
        errors.append("Password must contain at least one lowercase letter.")
    if not any(char in SPECIAL_CHARACTERS for char in password):
        errors.append("Password must contain at least one special character.")

    return errors
