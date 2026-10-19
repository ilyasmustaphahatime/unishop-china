"""Service business policy and actual unit-of-work boundaries over a stateful store.

The store isolates orchestration from SQL; real MySQL constraint and race proof
belongs to integration and live HTTP tests, not this in-memory test double.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.me.dependencies import safe_personal_operation
from app.services.favorites_service import FavoritesService
from app.services.personalization_errors import PersonalizationError
from app.services.recently_viewed_service import RecentlyViewedService

AT = datetime(2026, 10, 18, 1, 2, 3)


class MemorySession:
    def __init__(self):
        self.rows = {}
        self.durable = {}
        self.fail_commit = False

    def in_transaction(self):
        return True

    @contextmanager
    def begin_nested(self):
        before = deepcopy(self.rows)
        try:
            yield
        except Exception:
            self.rows = before
            raise

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("synthetic commit failure")
        self.durable = deepcopy(self.rows)

    def rollback(self):
        self.rows = deepcopy(self.durable)


class MemoryRepository:
    def __init__(self):
        self.public = {"one", "two", "three", "four"}
        self.fail_after_write = False

    def public_product_id(self, _db, slug):
        return slug if slug in self.public else None

    def entries_for_update(self, db, user):
        rows = [SimpleNamespace(product_listing_id=product, associated_at=at)
            for (owner, product), at in db.rows.items() if owner == user]
        return sorted(rows, key=lambda row: (row.associated_at, row.product_listing_id), reverse=True)

    def add(self, db, user, product, at):
        db.rows[(user, product)] = at
        if self.fail_after_write:
            raise RuntimeError("synthetic repository failure")

    def upsert(self, db, user, product, at):
        db.rows[(user, product)] = max(at, db.rows.get((user, product), at))
        if self.fail_after_write:
            raise RuntimeError("synthetic repository failure")

    def remove(self, db, user, slug):
        db.rows.pop((user, slug), None)

    def remove_entries(self, db, user, ids):
        for product in ids:
            db.rows.pop((user, product), None)

    def clear(self, db, user):
        self.remove_entries(db, user, [product for owner, product in db.rows if owner == user])


@pytest.fixture
def memory(monkeypatch):
    # User-row locking itself is proven by real MySQL tests; here identity
    # remains explicit while the service's real transaction helper is exercised.
    monkeypatch.setattr("app.services.favorites_service.lock_active_user", lambda *_: None)
    monkeypatch.setattr("app.services.recently_viewed_service.lock_active_user", lambda *_: None)
    return MemorySession(), MemoryRepository()


def test_favorite_idempotency_at_quota_preserves_original_timestamp(memory):
    db, repo = memory
    service = FavoritesService(codec=None, repository=repo, quota=2, clock=lambda: AT)
    assert service.add(db, "a", "one").favorited
    service.add(db, "a", "two")
    service.clock = lambda: AT + timedelta(hours=1)
    assert service.add(db, "a", "one").favorited
    assert db.rows[("a", "one")] == AT
    with pytest.raises(PersonalizationError) as denied:
        service.add(db, "a", "three")
    assert denied.value.status == 409
    assert db.rows == {("a", "one"): AT, ("a", "two"): AT}


def test_hidden_favorites_still_count_toward_quota(memory):
    db, repo = memory
    service = FavoritesService(codec=None, repository=repo, quota=1, clock=lambda: AT)
    service.add(db, "a", "one")
    repo.public.remove("one")
    with pytest.raises(PersonalizationError) as denied:
        service.add(db, "a", "two")
    assert denied.value.status == 409
    service.remove(db, "a", "one")
    service.remove(db, "a", "one")
    assert service.add(db, "a", "two").favorited


@pytest.mark.parametrize("kind", ["favorite", "recent"])
def test_unknown_product_does_not_write(memory, kind):
    db, repo = memory
    service = (FavoritesService if kind == "favorite" else RecentlyViewedService)(
        codec=None, repository=repo, clock=lambda: AT)
    with pytest.raises(PersonalizationError) as denied:
        (service.add if kind == "favorite" else service.record)(db, "a", "hidden")
    assert denied.value.status == 404
    assert db.rows == db.durable == {}


def test_recent_refresh_retention_ties_and_other_user_isolation(memory):
    db, repo = memory
    service = RecentlyViewedService(codec=None, repository=repo, retention=2, clock=lambda: AT)
    service.record(db, "a", "one")
    service.record(db, "a", "two")
    service.record(db, "b", "one")
    service.record(db, "a", "three")
    assert {product for user, product in db.rows if user == "a"} == {"two", "three"}
    assert ("b", "one") in db.rows
    service.clock = lambda: AT + timedelta(hours=1)
    service.record(db, "a", "three")
    assert db.rows[("a", "three")] > db.rows[("a", "two")]
    service.remove(db, "b", "three")
    assert ("a", "three") in db.rows
    service.clear(db, "a")
    service.clear(db, "a")
    assert db.rows == {("b", "one"): AT}


@pytest.mark.parametrize("kind", ["favorite", "recent"])
@pytest.mark.parametrize("failure", ["repository", "commit"])
def test_write_or_commit_failure_rolls_back_to_committed_state(memory, kind, failure):
    db, repo = memory
    service = (FavoritesService if kind == "favorite" else RecentlyViewedService)(
        codec=None, repository=repo, clock=lambda: AT)
    write = service.add if kind == "favorite" else service.record
    write(db, "a", "one")
    if failure == "repository":
        repo.fail_after_write = True
    else:
        db.fail_commit = True
    with pytest.raises(RuntimeError):
        write(db, "a", "two")
    assert db.rows == db.durable == {("a", "one"): AT}


def test_safe_http_mapping_keeps_business_status_and_hides_unexpected_detail():
    with pytest.raises(HTTPException) as expected:
        with safe_personal_operation():
            raise PersonalizationError("Saved listing limit reached.", 409)
    assert expected.value.status_code == 409
    with pytest.raises(HTTPException) as unexpected:
        with safe_personal_operation():
            raise RuntimeError("private database secret")
    assert unexpected.value.status_code == 503
    assert unexpected.value.detail == "Personal listing operation unavailable."
