"""Bounded contact identifier validation shared by transport and encryption."""
import re


def validate_wechat_contact(value: str) -> str:
    """Accept a WeChat ID, not arbitrary contact documents, HTML or phone numbers."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{5,19}", value):
        raise ValueError("Invalid WeChat ID.")
    return value
