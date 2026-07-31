import re

import phonenumbers
from phonenumbers import PhoneNumberFormat


def normalize_email_address(value: str) -> str:
    """Apply the canonical registration/login email normalization."""
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("An email address cannot be empty.")
    return normalized


def normalize_chinese_phone_number(value: str) -> str:
    """Validate a mainland Chinese mobile number and return E.164 format."""
    candidate = value.strip()
    if not candidate:
        raise ValueError("A phone number cannot be empty.")

    try:
        parsed = phonenumbers.parse(candidate, "CN")
    except phonenumbers.NumberParseException as exc:
        raise ValueError("Enter a valid mainland Chinese mobile number.") from exc

    normalized = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    if (
        not phonenumbers.is_possible_number(parsed)
        or not phonenumbers.is_valid_number(parsed)
        or phonenumbers.region_code_for_number(parsed) != "CN"
        or re.fullmatch(r"\+861[3-9]\d{9}", normalized) is None
    ):
        raise ValueError("Enter a valid mainland Chinese mobile number.")

    return normalized


def mask_phone_number(phone_number: str) -> str:
    """Mask a normalized phone number for safe operational messages."""
    if len(phone_number) < 8:
        return "***"
    return f"{phone_number[:3]}******{phone_number[-4:]}"


def validate_password_policy(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    if len(password) > 128:
        raise ValueError("Password must contain at most 128 characters.")
    if not any(character.isupper() for character in password):
        raise ValueError("Password must contain an uppercase letter.")
    if not any(character.islower() for character in password):
        raise ValueError("Password must contain a lowercase letter.")
    if not any(character.isdigit() for character in password):
        raise ValueError("Password must contain a digit.")
    return password
