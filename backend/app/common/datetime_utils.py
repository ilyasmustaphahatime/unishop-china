from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """Interpret naive database datetimes as UTC and normalize aware values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
