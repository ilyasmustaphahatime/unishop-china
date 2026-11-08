"""Pure money, cursor, immutability and contract security."""
from datetime import datetime
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.common.offers import OfferError, OfferPosition
from app.models import Deal, Offer
from app.schemas.offer import OfferCreate, OfferListQuery
from app.services.offer_cursor import OfferCursor
from tests.fixtures.conversations import chat_config


def payload(amount="12.00"):
    return dict(conversation_ref="cv-" + "a" * 32, amount=amount, client_offer_id=str(uuid4()))


@pytest.mark.parametrize("amount", [1, 1.2, True, False, None, "", "0", "0.00", "-1", "+1", "01", ".01", "1.",
    "1e2", "NaN", "Infinity", " 1", "1 ", "1.001", "10000000000.00", "１.00", {}, []])
def test_money_rejects_coercion_and_invalid_format(amount):
    with pytest.raises(ValidationError):
        OfferCreate(**payload(amount))


@pytest.mark.parametrize("amount,expected", [("0.01", "0.01"), ("1", "1.00"), ("12.3", "12.30"),
    ("9999999999.99", "9999999999.99")])
def test_exact_money(amount, expected):
    assert OfferCreate(**payload(amount)).amount == expected


@pytest.mark.parametrize("field", ["seller_id", "buyer_id", "proposer_role", "product_id", "status", "created_at", "expires_at"])
def test_mass_assignment(field):
    with pytest.raises(ValidationError):
        OfferCreate(**payload(), **{field: "untrusted"})


@pytest.mark.parametrize("client_id", ["", "A"*36, "not-a-uuid", 5, None, uuid4().hex])
def test_canonical_idempotency_key(client_id):
    body = payload()
    body["client_offer_id"] = client_id
    with pytest.raises(ValidationError):
        OfferCreate(**body)


def test_offer_terms_and_agreements_immutable():
    offer = Offer(amount="12.00", conversation_id="one", parent_offer_id=None)
    for key, value in (("amount", "15"), ("conversation_id", "two"), ("parent_offer_id", "parent")):
        with pytest.raises(ValueError):
            setattr(offer, key, value)
    deal = Deal(product_title_snapshot="Original title")
    with pytest.raises(ValueError):
        deal.product_title_snapshot = "Edited title"


def test_cursor_scope_tamper_and_filters():
    config, query = chat_config(), OfferListQuery()
    codec = OfferCursor(config, "actor", "offers", query)
    position = OfferPosition(datetime(2026, 1, 1), "of-" + "a" * 32)
    token = codec.encode(position)
    assert codec.decode(token) == position
    for actor, purpose, changed in [("other", "offers", query), ("actor", "deals", query),
            ("actor", "offers", OfferListQuery(limit=1)),
            ("actor", "offers", OfferListQuery(status="EXPIRED")),
            ("actor", "offers", OfferListQuery(role="seller")),
            ("actor", "offers", OfferListQuery(conversation_ref="cv-" + "b"*32))]:
        with pytest.raises(OfferError):
            OfferCursor(config, actor, purpose, changed).decode(token)
    for bad in ("", "a"*513, token + "=", token[:-4]+"xxxx", "a.b", [], None):
        with pytest.raises(OfferError):
            codec.decode(bad)


def test_cursor_missing_secret_fails_closed():
    with pytest.raises(OfferError) as exc:
        OfferCursor(chat_config(browse_cursor_signing_key=None), "actor", "offers", OfferListQuery())
    assert exc.value.status == 503
