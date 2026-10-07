"""Shared Unicode plain-text rules; field-specific meaning stays in each schema."""
import unicodedata

DIRECTION_CONTROL_CHARACTERS = {
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
}


def normalize_plain_text(
    value: str,
    *,
    field_name: str,
    maximum: int,
    allow_newlines: bool,
) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} is too long.")
    for character in normalized:
        category = unicodedata.category(character)
        if category == "Cs" or (
            category == "Cc" and not (allow_newlines and character in {"\n", "\t"})
        ):
            raise ValueError(f"{field_name} contains unsupported control characters.")
        if character in DIRECTION_CONTROL_CHARACTERS:
            raise ValueError(f"{field_name} contains unsupported direction controls.")
    return normalized
