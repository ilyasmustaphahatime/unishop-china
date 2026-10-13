"""Forced independent InnoDB interleavings at the save/final-metadata boundary."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus
from app.core.database import engine
from app.models import Category, City, SellerVerification, User, UserProfile
from app.models.seller_verification import VerificationStatus
from app.services.product_image_service import ProductImageError
from app.services.product_service import ProductService
from tests.integration.test_product_concurrency import world as world
from tests.integration.test_product_image_concurrency import media_world as media_world, call, current, race, upload
from tests.product_image_fixtures import raster


@pytest.mark.parametrize("initial,incoming", [(6, 4), (7, 3), (8, 2)])
def test_concurrent_multi_upload_quota_compensates_all_rejected_objects(media_world, initial, incoming):
    w = media_world
    for _ in range(initial):
        upload(w)
    outcomes = race(*(lambda db: w.service.upload(db, w.owner, w.slug, BytesIO(raster())) for _ in range(incoming)))
    assert sum(not isinstance(result, int) for result in outcomes) == 8 - initial
    assert outcomes.count(409) == incoming - (8 - initial)
    assert len(current(w)[1]) == 8


@pytest.mark.parametrize("revocation", ["approval", "account", "onboarding"])
def test_upload_vs_revocation_committed_in_metadata_gap_is_denied(media_world, monkeypatch, revocation):
    w = media_world
    saved, resume = Event(), Event()
    original = w.service._insert_metadata

    def controlled_insert(*args, **kwargs):
        saved.set()
        assert resume.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(w.service, "_insert_metadata", controlled_insert)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(lambda: call(lambda db: w.service.upload(db, w.owner, w.slug, BytesIO(raster()))))
        try:
            assert saved.wait(timeout=5)
            with Session(engine) as db, db.begin():
                if revocation == "account":
                    db.get(User, w.owner).account_status = AccountStatus.SUSPENDED
                elif revocation == "approval":
                    attempt = db.scalar(select(SellerVerification).where(SellerVerification.user_id == w.owner))
                    attempt.status, attempt.rejection_reason = VerificationStatus.REJECTED, "Synthetic audit revocation"
                else:
                    db.scalar(select(UserProfile).where(UserProfile.user_id == w.owner)).onboarding_completed = False
        finally:
            resume.set()
        assert pending.result(timeout=10) == (401 if revocation == "account" else 403)
    assert current(w)[1] == [] and list(w.storage.keys()) == []


@pytest.mark.parametrize("catalog", ["city", "category"])
def test_upload_vs_catalog_deactivation_keeps_public_bytes_hidden(media_world, monkeypatch, catalog):
    w = media_world
    call(lambda db: ProductService().transition(db, w.owner, w.slug, "publish"))
    saved, resume = Event(), Event()
    original = w.service._insert_metadata

    def controlled_insert(*args, **kwargs):
        saved.set()
        assert resume.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(w.service, "_insert_metadata", controlled_insert)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(lambda: call(lambda db: w.service.upload(db, w.owner, w.slug, BytesIO(raster()))))
        try:
            assert saved.wait(timeout=5)
            model, slug = (City, w.request.city_slug) if catalog == "city" else (Category, w.request.category_slug)
            with Session(engine) as db, db.begin():
                db.scalar(select(model).where(model.slug == slug)).is_active = False
        finally:
            resume.set()
        image = pending.result(timeout=10)
    assert not isinstance(image, int) and current(w)[1] == [image.ref]
    with Session(engine) as db:
        with pytest.raises(ProductImageError) as denied:
            w.service.read_public(db, w.slug, image.ref)
        assert denied.value.status == 404
    assert call(lambda db: w.service.read_owned(db, w.owner, w.slug, image.ref))[1] == "image/png"
