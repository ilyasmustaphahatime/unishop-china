"""Intentionally public navigation names, never authorization credentials."""

import re
import secrets

PUBLIC_HANDLE_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,28}[a-z0-9]$"
RESERVED_PUBLIC_HANDLES = frozenset({
    "admin", "api", "auth", "login", "logout", "register", "profile", "profiles",
    "users", "seller", "sellers", "settings", "account", "support", "help", "about",
    "search", "notifications", "messages", "chat", "products", "categories", "cities",
    "dev", "static", "assets",
})


def normalize_public_handle(value: str) -> str:
    # ASCII before lowercasing: never transliterate Unicode lookalikes into a handle.
    if not isinstance(value, str) or not value.isascii():
        raise ValueError("Invalid public handle.")
    normalized = value.lower()
    if (re.fullmatch(PUBLIC_HANDLE_PATTERN, normalized) is None
            or normalized in RESERVED_PUBLIC_HANDLES):
        raise ValueError("Invalid public handle.")
    return normalized


def generate_public_handle() -> str:
    # Neutral prefix + 80 independent random bits; no personal or row-derived data.
    return "user-" + secrets.token_hex(10)
