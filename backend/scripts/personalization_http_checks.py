"""Guarded Phase 12 real HTTP/MySQL checks with exact synthetic cleanup.

Run with ``python -m scripts.personalization_http_checks
--allow-development-synthetic-writes`` against a local development database.
The gate owns only newly generated users/listings/catalog rows, never prints
credentials or cursors, and compares all table contents before and after.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
from sqlalchemy import MetaData, delete, func, insert, select, update
from sqlalchemy.orm import Session

import app.models  # noqa: F401 -- register complete SQLAlchemy metadata
from app.common.enums import UserRoleType
from app.core.config import settings
from app.core.database import engine
from app.core.security import hash_password
from app.models import Category, City, ProductListing, SellerVerification, User, UserProfile, UserRole
from app.models.seller_verification import VerificationStatus

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE = "/api/v1/me"
FAVORITE_CAP = 5
HISTORY_CAP = 4


def database_fingerprint():
    """Hash all stored values; expose only table counts and digests, never rows."""
    metadata = MetaData()
    result = {}
    with engine.connect() as connection:
        metadata.reflect(bind=connection)
        for name, table in sorted(metadata.tables.items()):
            rows = [json.dumps([str(value) if value is not None else None for value in row],
                               ensure_ascii=True, separators=(",", ":"))
                    for row in connection.execute(select(table))]
            result[name] = (len(rows), hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest())
    return result


class Checks:
    def __init__(self):
        self.passed = []

    def require(self, condition, label):
        if not condition:
            raise AssertionError(label)
        self.passed.append(label)


def seed(marker, password):
    """Insert only this invocation's unique synthetic namespace."""
    ids = {"users": [str(uuid4()) for _ in range(3)], "category": str(uuid4()),
           "products": [str(uuid4()) for _ in range(12)],
           "slugs": ["item-" + uuid4().hex[:24] for _ in range(12)],
           "emails": [f"phase12-http-{marker}-{index}@example.com" for index in range(3)]}
    now = datetime.now(timezone.utc)
    with Session(engine) as db, db.begin():
        city = db.scalar(select(City).where(City.slug == "qingdao", City.is_active.is_(True)))
        if city is None:
            raise RuntimeError("Required migration-seeded active city unavailable.")
        digest = hash_password(password)
        for index, user_id in enumerate(ids["users"]):
            db.add(User(id=user_id, email=ids["emails"][index], password_hash=digest,
                        email_verified=index == 0, phone_verified=index == 0))
        db.flush()
        for user_id in ids["users"]:
            db.add(UserRole(user_id=user_id, role=UserRoleType.BUYER))
        seller_id = ids["users"][0]
        db.add(UserProfile(user_id=seller_id, display_name="Synthetic Phase Twelve",
                           city=city.name_en, city_id=city.id, onboarding_completed=True))
        db.add(SellerVerification(user_id=seller_id, status=VerificationStatus.VERIFIED,
                                  submitted_at=now, reviewed_at=now))
        db.add(Category(id=ids["category"], slug="phase12-http-" + marker[:16],
                        name_en="Synthetic Personal Lists", name_zh="Synthetic"))
        db.flush()
        for index, product_id in enumerate(ids["products"]):
            db.add(ProductListing(id=product_id, seller_user_id=seller_id,
                                  public_slug=ids["slugs"][index], title=f"Synthetic desk {index}",
                                  description="Synthetic Phase 12 HTTP verification listing.",
                                  price=Decimal("25.00"), currency="CNY", condition="good",
                                  status="PUBLISHED" if index < 11 else "DRAFT",
                                  city_id=city.id, category_id=ids["category"],
                                  published_at=now if index < 11 else None))
    return ids


def cleanup(ids):
    with Session(engine) as db, db.begin():
        db.execute(delete(ProductListing).where(ProductListing.id.in_(ids["products"]),
                                               ProductListing.seller_user_id == ids["users"][0]))
        db.execute(delete(User).where(User.id.in_(ids["users"]), User.email.in_(ids["emails"])))
        db.execute(delete(Category).where(Category.id == ids["category"]))


def associations(metadata):
    metadata.reflect(bind=engine, only=["product_favorites", "product_recent_views"])
    return metadata.tables["product_favorites"], metadata.tables["product_recent_views"]


def count(table, user_id):
    with engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(table).where(table.c.user_id == user_id))


def reset_lists(favorites, history, ids):
    with engine.begin() as connection:
        for table in (favorites, history):
            connection.execute(delete(table).where(table.c.user_id.in_(ids["users"])))


def start_server(storage):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = os.environ.copy()
    env.update({"APP_ENV": "development", "APP_DEBUG": "false",
                "PERSONAL_FAVORITES_LIMIT": str(FAVORITE_CAP),
                "PERSONAL_HISTORY_LIMIT": str(HISTORY_CAP),
                "SELLER_PRIVATE_STORAGE_DIR": str(Path(storage) / "seller"),
                "PRODUCT_IMAGE_STORAGE_DIR": str(Path(storage) / "products"),
                "PRODUCT_IMAGE_STORAGE_PROVIDER": "local"})
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--no-access-log", "--no-proxy-headers"],
        cwd=BACKEND_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=url, timeout=3, trust_env=False) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Synthetic HTTP server exited before readiness.")
                try:
                    if client.get("/api/v1/health/database").status_code == 200:
                        return process, url
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
        raise RuntimeError("Synthetic HTTP server readiness timed out.")
    except Exception:
        stop_server(process)
        raise


def stop_server(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def login(client, email, password, checks):
    response = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
    checks.require(response.status_code == 200, "real-login-status-" + str(response.status_code))
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]


def assert_private(response, checks, label):
    checks.require(response.headers.get("cache-control") == "no-store" and
                   response.headers.get("pragma") == "no-cache", label + ":private-cache")
    checks.require(all(value not in response.text for value in
                       ('"user_id"', '"seller_user_id"', '"storage_key"', '"product_listing_id"',
                        '"password_hash"', '"phone_number"', '"email"')), label + ":safe-fields")


def slugs(response):
    return [item["product"]["public_slug"] for item in response.json()["items"]]


def normal_checks(first, second, anonymous, checks, ids, favorites, history):
    product = ids["slugs"][0]
    missing = "item-" + uuid4().hex[:24]
    favorite_path = BASE + "/favorites/" + product
    history_path = BASE + "/recently-viewed/" + product
    for path in (BASE + "/favorites", BASE + "/recently-viewed"):
        response = anonymous.get(path)
        checks.require(response.status_code == 401, "missing-auth")
        assert_private(response, checks, "missing-auth")
        checks.require(anonymous.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401,
                       "invalid-auth")
    response = first.put(favorite_path)
    checks.require(response.status_code == 200 and response.json() == {"favorited": True}, "favorite-add")
    assert_private(response, checks, "favorite-add")
    with engine.connect() as connection:
        initial = connection.scalar(select(favorites.c.favorited_at).where(
            favorites.c.user_id == ids["users"][1], favorites.c.product_listing_id == ids["products"][0]))
    checks.require(first.put(favorite_path).status_code == 200, "favorite-repeat-success")
    with engine.connect() as connection:
        checks.require(connection.scalar(select(favorites.c.favorited_at).where(
            favorites.c.user_id == ids["users"][1], favorites.c.product_listing_id == ids["products"][0])) == initial,
            "favorite-repeat-timestamp-preserved")
    response = first.get(BASE + "/favorites")
    checks.require(response.status_code == 200 and slugs(response) == [product], "favorite-list")
    assert_private(response, checks, "favorite-list")
    checks.require(second.get(BASE + "/favorites").json()["items"] == [], "favorite-user-isolation")
    checks.require(second.delete(favorite_path).status_code == 204 and count(favorites, ids["users"][1]) == 1,
                   "favorite-cross-user-delete-isolation")
    lookup = first.post(BASE + "/favorites/lookup", json={"product_slugs": [product, missing]})
    checks.require(lookup.status_code == 200 and lookup.json() == {"favorites": {product: True, missing: False}},
                   "favorite-lookup")
    assert_private(lookup, checks, "favorite-lookup")
    checks.require(first.post(history_path).status_code == 204, "history-record")
    with engine.connect() as connection:
        initial = connection.scalar(select(history.c.last_viewed_at).where(history.c.user_id == ids["users"][1]))
    checks.require(first.post(history_path).status_code == 204, "history-repeat")
    with engine.connect() as connection:
        checks.require(connection.scalar(select(history.c.last_viewed_at).where(
            history.c.user_id == ids["users"][1])) >= initial, "history-refresh-monotonic")
    checks.require(count(history, ids["users"][1]) == 1, "history-unique-pair")
    history_response = first.get(BASE + "/recently-viewed")
    checks.require(slugs(history_response) == [product], "history-list")
    assert_private(history_response, checks, "history-list")
    checks.require(second.get(BASE + "/recently-viewed").json()["items"] == [], "history-user-isolation")
    checks.require(second.delete(BASE + "/recently-viewed").status_code == 204 and
                   count(history, ids["users"][1]) == 1, "history-cross-user-clear-isolation")
    before_get = count(history, ids["users"][1])
    checks.require(anonymous.get("/api/v1/products/" + ids["slugs"][1]).status_code == 200 and
                   count(history, ids["users"][1]) == before_get, "public-get-read-only")
    with engine.begin() as connection:
        connection.execute(update(ProductListing).where(ProductListing.id == ids["products"][0]).values(status="PAUSED"))
    checks.require(anonymous.get("/api/v1/products/" + product).status_code == 404, "canonical-hidden")
    checks.require(first.get(BASE + "/favorites").json()["items"] == [] and
                   first.get(BASE + "/recently-viewed").json()["items"] == [], "hidden-filtered-both-lists")
    checks.require(first.post(BASE + "/favorites/lookup", json={"product_slugs": [product]}).json() ==
                   {"favorites": {product: False}}, "hidden-lookup-undisclosed")
    checks.require(first.put(favorite_path).status_code == 404 and first.post(history_path).status_code == 404,
                   "hidden-write-denied")
    checks.require(count(favorites, ids["users"][1]) == 1 and count(history, ids["users"][1]) == 1,
                   "hidden-associations-retained")
    with engine.begin() as connection:
        connection.execute(update(ProductListing).where(ProductListing.id == ids["products"][0]).values(status="PUBLISHED"))
    checks.require(slugs(first.get(BASE + "/favorites")) == [product] and
                   slugs(first.get(BASE + "/recently-viewed")) == [product], "republish-associations-reappear")
    checks.require(first.delete(favorite_path).status_code == 204 and first.delete(favorite_path).status_code == 204,
                   "favorite-delete-idempotent")
    checks.require(first.delete(history_path).status_code == 204 and first.delete(history_path).status_code == 204,
                   "history-delete-idempotent")
    checks.require(first.delete(BASE + "/recently-viewed").status_code == 204 and
                   first.delete(BASE + "/recently-viewed").status_code == 204, "history-clear-idempotent")
    checks.require(first.put(BASE + "/favorites/" + missing).status_code == 404 and
                   first.post(BASE + "/recently-viewed/" + missing).status_code == 404, "unknown-product-generic")
    for body in ({"product_slugs": []}, {"product_slugs": [product, product]},
                 {"product_slugs": [product], "user_id": ids["users"][2]},
                 {"product_slugs": ["item-" + uuid4().hex[:24] for _ in range(51)]}):
        checks.require(first.post(BASE + "/favorites/lookup", json=body).status_code == 422, "lookup-validation")
    checks.require(first.post(BASE + "/favorites/lookup", content=b"{",
                              headers={"Content-Type": "application/json"}).status_code == 422, "malformed-json")
    checks.require(first.post(BASE + "/favorites/lookup", content=b"x" * 4097,
                              headers={"Content-Type": "application/json"}).status_code == 413, "oversized-body")
    for params in ({"limit": 0}, {"limit": 51}, {"user_id": ids["users"][2]},
                   [("limit", "1"), ("limit", "2")]):
        checks.require(first.get(BASE + "/favorites", params=params).status_code == 422, "query-validation")
    checks.require(first.get(BASE + "/favorites", params={"cursor": "tampered"}).status_code == 400,
                   "cursor-invalid")
    checks.require(first.get(BASE + "/favorites", params={"cursor": "a" * 513}).status_code == 422,
                   "cursor-oversized")
    checks.require(first.put(BASE + "/favorites/not-a-slug").status_code == 422, "slug-validation")
    checks.require(first.put(favorite_path, json={"user_id": ids["users"][2]}).status_code == 422,
                   "bodyless-write-rejects-authority")


def pagination_checks(first, second, checks, ids, favorites, history):
    reset_lists(favorites, history, ids)
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        for table, timestamp in ((favorites, "favorited_at"), (history, "last_viewed_at")):
            connection.execute(insert(table), [{"user_id": ids["users"][1], "product_listing_id": product_id,
                                                timestamp: now} for product_id in ids["products"][:4]])
    for endpoint in ("favorites", "recently-viewed"):
        path = BASE + "/" + endpoint
        response = first.get(path, params={"limit": 1})
        checks.require(response.status_code == 200, endpoint + ":first-page")
        cursor = response.json()["next_cursor"]
        checks.require(bool(cursor), endpoint + ":cursor-present")
        checks.require(second.get(path, params={"limit": 1, "cursor": cursor}).status_code == 400,
                       endpoint + ":cross-user-cursor-rejected")
        other = "recently-viewed" if endpoint == "favorites" else "favorites"
        checks.require(first.get(BASE + "/" + other, params={"limit": 1, "cursor": cursor}).status_code == 400,
                       endpoint + ":cross-module-cursor-rejected")
        checks.require(first.get(path, params={"limit": 2, "cursor": cursor}).status_code == 400,
                       endpoint + ":page-size-bound")
        tampered = ("a" if cursor[0] != "a" else "b") + cursor[1:]
        checks.require(first.get(path, params={"limit": 1, "cursor": tampered}).status_code == 400,
                       endpoint + ":signature-tampering-rejected")
        seen = slugs(response)
        for _ in range(5):
            if cursor is None:
                break
            response = first.get(path, params={"limit": 1, "cursor": cursor})
            checks.require(response.status_code == 200, endpoint + ":continuation")
            seen.extend(slugs(response))
            cursor = response.json()["next_cursor"]
        checks.require(cursor is None and len(seen) == 4 and set(seen) == set(ids["slugs"][:4]),
                       endpoint + ":equal-timestamp-exact-pagination")


def parallel(client, method, paths):
    with ThreadPoolExecutor(max_workers=len(paths)) as pool:
        return list(pool.map(lambda path: client.request(method, path).status_code, paths))


def rate_limit_check(client, checks):
    for _ in range(125):
        response = client.get(BASE + "/favorites")
        if response.status_code == 429:
            checks.require(response.headers.get("retry-after", "").isdigit(), "live-rate-limit-retry-after")
            assert_private(response, checks, "live-rate-limit")
            return
        checks.require(response.status_code == 200, "pre-rate-limit-valid-read")
    raise AssertionError("live-rate-limit-not-enforced")


def race_checks(first, second, checks, ids, favorites, history, round_number):
    reset_lists(favorites, history, ids)
    actor = ids["users"][1]
    other_actor = ids["users"][2]
    prefix = f"race-round-{round_number}:"
    favorite_paths = [BASE + "/favorites/" + slug for slug in ids["slugs"]]
    history_paths = [BASE + "/recently-viewed/" + slug for slug in ids["slugs"]]
    checks.require(first.put(favorite_paths[0]).status_code == 200, prefix + "favorite-initial")
    with engine.connect() as connection:
        original = connection.scalar(select(favorites.c.favorited_at).where(favorites.c.user_id == actor))
    statuses = parallel(first, "PUT", [favorite_paths[0]] * 5)
    with engine.connect() as connection:
        unchanged = connection.scalar(select(favorites.c.favorited_at).where(favorites.c.user_id == actor)) == original
    checks.require(statuses == [200] * 5 and count(favorites, actor) == 1 and unchanged,
                   prefix + "A-same-favorite-one-row-original-time")
    reset_lists(favorites, history, ids)
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(insert(favorites), [{"user_id": actor, "product_listing_id": product_id,
                                                "favorited_at": now} for product_id in ids["products"][:4]])
    statuses = parallel(first, "PUT", favorite_paths[4:9])
    checks.require(statuses.count(200) == 1 and all(status in {200, 409} for status in statuses) and
                   count(favorites, actor) == FAVORITE_CAP, prefix + "B-quota-boundary")
    checks.require(first.put(favorite_paths[0]).status_code == 200, prefix + "quota-existing-idempotent")
    statuses = parallel(first, "POST", [history_paths[0]] * 5)
    checks.require(statuses == [204] * 5 and count(history, actor) == 1,
                   prefix + "C-same-view-one-row")
    with engine.begin() as connection:
        connection.execute(delete(history).where(history.c.user_id == actor))
        connection.execute(insert(history), [{"user_id": actor, "product_listing_id": product_id,
                                              "last_viewed_at": now - timedelta(minutes=1)}
                                             for product_id in ids["products"][:4]])
        connection.execute(insert(history), {"user_id": other_actor,
                                             "product_listing_id": ids["products"][0], "last_viewed_at": now})
    statuses = parallel(first, "POST", history_paths[4:9])
    with engine.connect() as connection:
        retained = set(connection.scalars(select(history.c.product_listing_id).where(history.c.user_id == actor)))
    checks.require(statuses == [204] * 5 and len(retained) == HISTORY_CAP and
                   retained.issubset(set(ids["products"][4:9])) and count(history, other_actor) == 1,
                   prefix + "D-bounded-retention-user-isolation")
    with ThreadPoolExecutor(max_workers=2) as pool:
        clear = pool.submit(first.delete, BASE + "/recently-viewed")
        record = pool.submit(first.post, history_paths[9])
        statuses = [clear.result().status_code, record.result().status_code]
    with engine.connect() as connection:
        final = list(connection.scalars(select(history.c.product_listing_id).where(history.c.user_id == actor)))
    checks.require(statuses == [204, 204] and final in ([], [ids["products"][9]]) and
                   count(history, other_actor) == 1, prefix + "E-clear-record-serial-order")
    checks.require(second.get(BASE + "/recently-viewed").status_code == 200,
                   prefix + "other-user-remains-readable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-development-synthetic-writes", action="store_true")
    parser.add_argument("--race-runs", type=int, choices=range(1, 4), default=3)
    args = parser.parse_args()
    if (not args.allow_development_synthetic_writes or settings.app_env.strip().lower() != "development"
            or engine.url.database != "unishop_china"
            or engine.url.host not in {"localhost", "127.0.0.1", "::1"}):
        parser.error("Refused: explicit local-development synthetic-write consent required.")
    before = database_fingerprint()
    metadata = MetaData()
    favorites, history = associations(metadata)
    checks = Checks()
    marker = uuid4().hex
    password = secrets.token_urlsafe(32) + "Aa1"
    ids = None
    process = None
    stage = "synthetic-seed"
    result = 1
    with tempfile.TemporaryDirectory(prefix="unishop-phase12-http-") as storage:
        try:
            ids = seed(marker, password)
            for round_number in range(args.race_runs + 1):
                stage = "startup"
                process, url = start_server(storage)
                with httpx.Client(base_url=url, timeout=20, trust_env=False) as first, \
                        httpx.Client(base_url=url, timeout=20, trust_env=False) as second, \
                        httpx.Client(base_url=url, timeout=20, trust_env=False) as anonymous:
                    login(first, ids["emails"][1], password, checks)
                    login(second, ids["emails"][2], password, checks)
                    if round_number == 0:
                        stage = "normal-security-http"
                        normal_checks(first, second, anonymous, checks, ids, favorites, history)
                        stage = "signed-private-pagination"
                        pagination_checks(first, second, checks, ids, favorites, history)
                        stage = "live-abuse-limit"
                        rate_limit_check(first, checks)
                    else:
                        stage = f"concurrency-{round_number}"
                        race_checks(first, second, checks, ids, favorites, history, round_number)
                stop_server(process)
                process = None
            result = 0
        except Exception as error:
            # Never stringify an HTTP/DB exception: it can contain private inputs.
            print(json.dumps({"status": "FAIL", "stage": stage, "error_type": type(error).__name__,
                              "failed_check": str(error) if isinstance(error, AssertionError) else None}))
        finally:
            if process is not None:
                stop_server(process)
            if ids is not None:
                cleanup(ids)
            preserved = database_fingerprint() == before
            media_clean = not any(path.is_file() for path in Path(storage).rglob("*"))
            print(json.dumps({"checks_passed": len(checks.passed), "labels": checks.passed,
                              "race_runs": args.race_runs, "data_preserved": preserved,
                              "synthetic_cleanup": preserved, "media_clean": media_clean,
                              "servers_stopped": process is None or process.poll() is not None}))
            if not preserved or not media_clean:
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
