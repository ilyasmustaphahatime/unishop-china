"""Independent Phase 9 fault injection and exact-money regressions on MySQL."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import City, ProductListing
from app.repositories.product_repository import ProductRepository
from tests.integration.test_product_listings import (
    OWN, PUBLIC, action, body, create, headers, world as world,
)


@pytest.mark.parametrize("operation", ["create", "update", "publish", "pause", "archive"])
def test_commit_failure_preserves_listing_and_recovers_same_session(world, monkeypatch, operation):
    client, db, owner, _, _ = world
    slug = create(world)["public_slug"]
    if operation == "pause":
        assert action(world, slug, "publish").status_code == 200
    original = client.get(OWN + "/" + slug, headers=headers(owner)).json()

    def request():
        if operation == "create":
            return client.post(OWN, headers=headers(owner), json=body())
        if operation == "update":
            return client.patch(OWN + "/" + slug, headers=headers(owner), json={"title": "Committed replacement"})
        return action(world, slug, operation)

    def fail_commit():
        raise RuntimeError("SYNTHETIC COMMIT FAILURE: must not be reflected")

    with monkeypatch.context() as fault:
        fault.setattr(db, "commit", fail_commit)
        failed = request()
    assert failed.status_code == 503
    assert failed.json() == {"detail": "Listing operation unavailable."}
    assert failed.headers["cache-control"] == "no-store"
    assert db.is_active
    assert client.get(OWN + "/" + slug, headers=headers(owner)).json() == original
    assert db.scalar(select(func.count()).select_from(ProductListing).where(
        ProductListing.seller_user_id == owner.id)) == 1
    recovered = request()
    assert recovered.status_code == (201 if operation == "create" else 200)


@pytest.mark.parametrize("price", ["0.01", "0.10", "0.30", "19.99", "999999.99"])
def test_money_round_trip_is_exact_in_database_owner_and_public_http(world, price):
    client, db, _, _, _ = world
    slug = create(world, price=price)["public_slug"]
    stored = db.scalar(select(ProductListing.price).where(ProductListing.public_slug == slug))
    assert isinstance(stored, Decimal) and stored == Decimal(price)
    published = action(world, slug, "publish")
    assert published.status_code == 200 and published.json()["price"] == price
    public = client.get(PUBLIC + slug)
    assert public.status_code == 200 and public.json()["price"] == price


def test_unrelated_real_foreign_key_integrity_failure_is_not_retried(world, monkeypatch):
    _, db, _, _, category = world
    candidates = []

    def candidate():
        candidates.append("item-" + uuid4().hex[:24])
        return candidates[-1]

    monkeypatch.setattr("app.repositories.product_repository.generate_product_slug", candidate)
    with pytest.raises(IntegrityError) as error:
        ProductRepository().create(db, seller_user_id=str(uuid4()), title="Synthetic FK failure",
            description="Must not retry an unrelated foreign key failure.", price=Decimal("1.00"),
            condition="good", currency="CNY", status="DRAFT", category_id=category.id,
            city_id=db.scalar(select(City.id).where(City.slug == "qingdao")))
    assert error.value.orig.args[0] == 1452
    assert len(candidates) == 1 and db.is_active
    assert create(world)["status"] == "DRAFT"


@pytest.mark.parametrize("field", ["owner_id", "role"])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_additional_authority_fields_are_rejected_without_reflection(world, field, operation):
    client, _, owner, _, _ = world
    slug = create(world)["public_slug"]
    payload = {**(body() if operation == "create" else {"title": "Changed title"}), field: "PRIVATE ATTACK INPUT"}
    response = (client.post(OWN, headers=headers(owner), json=payload) if operation == "create" else
                client.patch(OWN + "/" + slug, headers=headers(owner), json=payload))
    assert response.status_code == 422 and "PRIVATE ATTACK INPUT" not in response.text
    assert client.get(OWN + "/" + slug, headers=headers(owner)).json()["title"] == body()["title"]
