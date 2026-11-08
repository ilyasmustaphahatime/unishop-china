"""Real InnoDB transactions; every committed synthetic world is exactly cleaned."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from app.common.offers import OfferError
from app.core.database import engine
from app.core.offer_limits import clear_offer_limits
from app.models import Deal, Offer, ProductListing, User
from app.services.offer_service import OfferService
from app.services.product_service import ProductError, ProductService
from scripts.personalization_http_checks import database_fingerprint
from tests.fixtures.conversations import chat_config
from tests.fixtures.offers import cleanup_offer_world, seed_offer_world


@pytest.fixture
def committed_world():
    clear_offer_limits()
    baseline = database_fingerprint()
    with Session(engine, expire_on_commit=False) as db, db.begin():
        world, refs = seed_offer_world(db)
    try:
        yield world, refs, chat_config()
    finally:
        with Session(engine) as db, db.begin():
            cleanup_offer_world(db, world)
        clear_offer_limits()
        assert database_fingerprint() == baseline, "Offer race cleanup changed pre-existing data."


def race(actor, operations):
    barrier = Barrier(len(operations))
    def run(operation):
        with Session(engine) as db:
            db.scalar(select(User.id).where(User.id == actor))
            barrier.wait(timeout=15)
            try:
                return operation(db)
            except OfferError as error:
                return error.status
            except ProductError as error:
                return error.status
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, operation) for operation in operations]
        return [future.result(timeout=30) for future in futures]


def create(world, index=0, actor=None):
    data, refs, config = world
    with Session(engine) as db:
        return OfferService(db, config).create(actor or data.buyer.id, {
            "conversation_ref": refs[index], "amount": "25.50", "client_offer_id": str(uuid4())})[0]


def assert_consistent(data, expected_deals):
    with Session(engine) as db:
        offers = list(db.scalars(select(Offer).where(Offer.product_listing_id == data.products[0].id)))
        deals = list(db.scalars(select(Deal).where(Deal.product_listing_id == data.products[0].id)))
        assert len(deals) == expected_deals
        assert sum(row.status == "ACCEPTED" for row in offers) == len(deals)
        if deals:
            assert db.get(ProductListing, data.products[0].id).status == "ARCHIVED"
            assert not any(row.status == "PENDING" for row in offers)
            assert deals[0].accepted_offer_id in {row.id for row in offers if row.status == "ACCEPTED"}


@pytest.mark.parametrize("conflict", [False, True])
def test_concurrent_create_idempotency(committed_world, conflict):
    data, refs, config = committed_world
    key = str(uuid4())
    results = race(data.buyer.id, [lambda db, amount=amount: OfferService(db, config).create(data.buyer.id,
        {"conversation_ref": refs[0], "amount": amount, "client_offer_id": key})
        for amount in (["1", "2"] if conflict else ["1"] * 5)])
    if conflict:
        assert results.count(409) == 1
    successes = [result for result in results if not isinstance(result, int)]
    assert sum(created for _, created in successes) == 1
    assert len({row.offer_ref for row, _ in successes}) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Offer).where(Offer.product_listing_id == data.products[0].id)) == 1


@pytest.mark.parametrize("identical", [True, False])
def test_concurrent_counter_has_one_child(committed_world, identical):
    data, _, config = committed_world
    root = create(committed_world)
    key = str(uuid4())
    results = race(data.seller.id, [lambda db, key=key: OfferService(db, config).counter(data.seller.id,
        root.offer_ref, {"amount": "30", "client_offer_id": key})
        for key in (key, key if identical else str(uuid4()))])
    assert results.count(409) == (0 if identical else 1)
    successes = [r for r in results if not isinstance(r, int)]
    assert sum(created for _, created in successes) == 1
    with Session(engine) as db:
        rows = list(db.scalars(select(Offer).where(Offer.product_listing_id == data.products[0].id)))
        assert sorted(row.status for row in rows) == ["COUNTERED", "PENDING"]


def test_two_buyers_compete_for_exactly_one_agreement(committed_world):
    data, _, config = committed_world
    first = create(committed_world)
    other = create(committed_world, 5, data.outsider.id)
    results = race(data.seller.id, [lambda db, ref=ref: OfferService(db, config).transition(data.seller.id, ref, "accept")
                                    for ref in (first.offer_ref, other.offer_ref)])
    assert results.count(409) == 1
    assert_consistent(data, 1)


@pytest.mark.parametrize("other", ["accept", "reject", "withdraw", "counter", "archive"])
def test_acceptance_races_terminal_operations(committed_world, other):
    data, _, config = committed_world
    proposal = create(committed_world)
    def competing(db):
        service = OfferService(db, config)
        if other == "archive":
            return ProductService().transition(db, data.seller.id, data.products[0].public_slug, "archive")
        if other == "counter":
            return service.counter(data.seller.id, proposal.offer_ref, {"amount": "30", "client_offer_id": str(uuid4())})
        actor = data.buyer.id if other == "withdraw" else data.seller.id
        return service.transition(actor, proposal.offer_ref, other)
    results = race(data.seller.id, [lambda db: OfferService(db, config).transition(data.seller.id, proposal.offer_ref, "accept"), competing])
    if other == "accept":
        assert all(not isinstance(r, int) for r in results)
        assert results[0].deal_ref == results[1].deal_ref
    elif other == "archive":
        assert results[0] == 409 or not isinstance(results[0], int)
        assert results[1] == 409 or not isinstance(results[1], int)
    else:
        assert results.count(409) == 1
    assert_consistent(data, int(not isinstance(results[0], int)))


def test_expiration_is_rechecked_after_waiting_for_product_lock(committed_world, monkeypatch):
    data, _, config = committed_world
    proposal = create(committed_world)
    deadline = datetime(2030, 1, 1, tzinfo=timezone.utc)
    at = deadline.replace(tzinfo=None)
    with Session(engine) as db, db.begin():
        db.execute(update(Offer).where(Offer.public_ref == proposal.offer_ref)
                   .values(created_at=at-timedelta(days=1), expires_at=at))
    expired, waiting = Event(), Event()
    monkeypatch.setattr("app.services.offer_service.utc_now", lambda: deadline if expired.is_set() else deadline-timedelta(seconds=1))
    def attempt():
        with Session(engine) as db:
            connection = db.connection()
            def before(conn, cursor, statement, parameters, context, many):
                if "product_listings" in statement and "FOR UPDATE" in statement:
                    waiting.set()
            event.listen(connection, "before_cursor_execute", before)
            try:
                return OfferService(db, config).transition(data.seller.id, proposal.offer_ref, "accept")
            except OfferError as error:
                return error.status
            finally:
                event.remove(connection, "before_cursor_execute", before)
    with Session(engine) as holder:
        holder.scalar(select(ProductListing).where(ProductListing.id == data.products[0].id).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(attempt)
            try:
                assert waiting.wait(10), "Acceptance did not reach the locked product."
                assert not future.done()
                expired.set()
            finally:
                holder.rollback()
            assert future.result(timeout=20) == 409
    assert_consistent(data, 0)
