"""Neutral keyset value types shared by SQL repositories and cursor codecs."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BrowsePosition:
    value: datetime | Decimal
    slug: str


@dataclass(frozen=True, slots=True)
class PersonalizationPosition:
    value: datetime
    slug: str
