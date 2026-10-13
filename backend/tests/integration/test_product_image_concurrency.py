"""Independent real InnoDB sessions and real temporary object writes."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier, local
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus
from app.core.authorization import AuthorizationError
from app.core.database import engine
from app.models import ProductImage, ProductListing, SellerVerification, User, UserProfile
from app.models.seller_verification import VerificationStatus
from app.schemas.product_image import ProductImageOrder
from app.services.product_service import ProductService, ProductError
from app.services.catalog_service import CatalogError
from app.services.product_image_service import ProductImageService, ProductImageError
from app.services.product_image_storage import LocalProductImageStorage
from tests.product_image_fixtures import raster
from tests.integration.test_product_concurrency import world as world


@pytest.fixture
def media_world(world,tmp_path):
    _,users,request=world
    storage=LocalProductImageStorage(tmp_path/"race-media")
    service=ProductImageService(storage)
    slug=call(lambda db: ProductService().create(db,users[0],request)).public_slug
    try:
        yield SimpleNamespace(service=service,storage=storage,slug=slug,owner=users[0],other=users[1],request=request)
    finally:
        for key in list(storage.keys()):
            storage.delete(key)
        assert list(storage.keys())==[]


def call(operation):
    with Session(engine) as db:
        try:
            return operation(db)
        except (ProductImageError,ProductError,AuthorizationError,CatalogError) as error:
            return error.status


def race(*operations):
    barrier=Barrier(len(operations))
    def worker(operation):
        barrier.wait(timeout=10)
        return call(operation)
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return [future.result(timeout=30) for future in [pool.submit(worker,operation) for operation in operations]]


def upload(w):
    return call(lambda db: w.service.upload(db,w.owner,w.slug,BytesIO(raster())))


def current(w):
    with Session(engine) as db:
        product=db.scalar(select(ProductListing).where(ProductListing.public_slug==w.slug))
        rows=list(db.scalars(select(ProductImage).where(ProductImage.product_listing_id==product.id).order_by(ProductImage.position)))
        assert [row.position for row in rows]==list(range(len(rows))) and len(rows)<=8
        assert {row.storage_key for row in rows}==set(w.storage.keys())
        return product.status,[row.public_ref for row in rows]


def test_concurrent_upload_at_limit_cannot_create_ninth_image(media_world):
    w=media_world
    for _ in range(7):
        upload(w)
    outcomes=race(*(lambda db: w.service.upload(db,w.owner,w.slug,BytesIO(raster())) for _ in range(2)))
    assert outcomes.count(409)==1 and len(current(w)[1])==8


def test_upload_vs_archive_uses_current_locked_state(media_world):
    w=media_world
    outcomes=race(lambda db: w.service.upload(db,w.owner,w.slug,BytesIO(raster())),
                  lambda db: ProductService().transition(db,w.owner,w.slug,"archive"))
    assert not isinstance(outcomes[1],int)
    assert not isinstance(outcomes[0],int) or outcomes[0]==409
    status,refs=current(w)
    assert status=="ARCHIVED" and len(refs)==(0 if outcomes[0]==409 else 1)


def test_upload_vs_delete_keeps_new_image_and_contiguous_cover(media_world):
    w=media_world
    original=upload(w).ref
    outcomes=race(lambda db: w.service.upload(db,w.owner,w.slug,BytesIO(raster())),
                  lambda db: w.service.delete(db,w.owner,w.slug,original))
    assert not any(isinstance(outcome,int) for outcome in outcomes)
    assert current(w)[1]==[outcomes[0].ref]


def test_delete_vs_reorder_has_only_serial_outcomes(media_world):
    w=media_world
    refs=[upload(w).ref for _ in range(2)]
    outcomes=race(lambda db: w.service.delete(db,w.owner,w.slug,refs[0]),
                  lambda db: w.service.reorder(db,w.owner,w.slug,ProductImageOrder(images=refs[::-1])))
    assert outcomes[0] is None and (not isinstance(outcomes[1],int) or outcomes[1]==409)
    assert current(w)[1]==[refs[1]]


def test_delete_vs_delete_returns_one_success_and_one_not_found(media_world):
    w=media_world
    ref=upload(w).ref
    outcomes=race(*(lambda db: w.service.delete(db,w.owner,w.slug,ref) for _ in range(2)))
    assert outcomes.count(None)==1 and outcomes.count(404)==1 and current(w)[1]==[]


def test_reorder_vs_reorder_is_one_complete_order_never_a_mixture(media_world):
    w=media_world
    refs=[upload(w).ref for _ in range(3)]
    orders=[refs[::-1],refs[1:]+refs[:1]]
    outcomes=race(*(lambda db,order=order: w.service.reorder(db,w.owner,w.slug,ProductImageOrder(images=order)) for order in orders))
    assert all(not isinstance(outcome,int) for outcome in outcomes)
    assert current(w)[1] in orders


def test_reorder_vs_archive_preserves_terminal_policy(media_world):
    w=media_world
    refs=[upload(w).ref for _ in range(2)]
    outcomes=race(lambda db: w.service.reorder(db,w.owner,w.slug,ProductImageOrder(images=refs[::-1])),
                  lambda db: ProductService().transition(db,w.owner,w.slug,"archive"))
    status,final=current(w)
    assert status=="ARCHIVED"
    assert final==(refs if outcomes[0]==409 else refs[::-1])


@pytest.mark.parametrize("kind", ["archive","verification","account","onboarding","count"])
def test_stale_orm_snapshot_cannot_authorize_image_upload(media_world,kind):
    w=media_world
    for _ in range(7 if kind=="count" else 1):
        upload(w)
    with Session(engine) as stale:
        cached=[stale.get(User,w.owner),
            stale.scalar(select(ProductListing).where(ProductListing.public_slug==w.slug)),
            stale.scalar(select(SellerVerification).where(SellerVerification.user_id==w.owner)),
            stale.scalar(select(UserProfile).where(UserProfile.user_id==w.owner))]
        cached.extend(stale.scalars(select(ProductImage).where(ProductImage.product_listing_id==cached[1].id)))
        if kind=="count":
            upload(w)
        elif kind=="archive":
            call(lambda db: ProductService().transition(db,w.owner,w.slug,"archive"))
        else:
            with Session(engine) as changed,changed.begin():
                if kind=="account":
                    changed.get(User,w.owner).account_status=AccountStatus.SUSPENDED
                elif kind=="verification":
                    row=changed.scalar(select(SellerVerification).where(SellerVerification.user_id==w.owner))
                    row.status,row.rejection_reason=VerificationStatus.REJECTED,"Synthetic revocation"
                else:
                    changed.scalar(select(UserProfile).where(UserProfile.user_id==w.owner)).onboarding_completed=False
        with pytest.raises((ProductImageError,AuthorizationError,ProductError)) as error:
            w.service.upload(stale,w.owner,w.slug,BytesIO(raster()))
        assert error.value.status==(401 if kind=="account" else 403 if kind in {"verification","onboarding"} else 409)
    assert len(current(w)[1])==(8 if kind=="count" else 1)


def test_public_ref_collision_across_sellers_retries_unique_constraint(media_world,monkeypatch):
    w=media_world
    second_slug=call(lambda db: ProductService().create(db,w.other,w.request)).public_slug
    from app.common.product_image_rules import generate_image_ref
    state=local()
    def ref():
        count=getattr(state,"count",0)
        state.count=count+1
        return "img-"+"a"*32 if count==0 else generate_image_ref()
    monkeypatch.setattr("app.repositories.product_image_repository.generate_image_ref",ref)
    outcomes=race(lambda db: w.service.upload(db,w.owner,w.slug,BytesIO(raster())),
                  lambda db: w.service.upload(db,w.other,second_slug,BytesIO(raster())))
    assert all(not isinstance(outcome,int) for outcome in outcomes)
    assert len({outcome.ref for outcome in outcomes})==2 and len(list(w.storage.keys()))==2
