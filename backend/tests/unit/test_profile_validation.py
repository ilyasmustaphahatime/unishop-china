import pytest
from pydantic import ValidationError

from app.schemas.profile import ProfileUpdateRequest


@pytest.mark.parametrize("value", ["", " ", "x", "x" * 51, "safe\x00name", "safe\u202ename"])
def test_display_name_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(display_name=value)


def test_profile_text_is_trimmed_normalized_and_unicode_safe() -> None:
    request = ProfileUpdateRequest(
        display_name="  Jose\u0301 Li  ",
        bio="  International student in Qingdao.  ",
        city="Qingdao",
    )

    assert request.display_name == "Jos\u00e9 Li"
    assert request.bio == "International student in Qingdao."


def test_empty_bio_becomes_null() -> None:
    assert ProfileUpdateRequest(bio="  ").bio is None


def test_plain_text_xss_values_are_not_interpreted_or_destroyed() -> None:
    request = ProfileUpdateRequest(
        display_name="<script>alert(1)</script>",
        bio="<img src=x onerror=alert(1)> &amp; javascript:...",
    )

    assert request.display_name == "<script>alert(1)</script>"
    assert request.bio == "<img src=x onerror=alert(1)> &amp; javascript:..."


def test_invalid_city_and_mass_assignment_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(city="Wuhan")
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(display_name="Valid Name", account_status="ACTIVE")
