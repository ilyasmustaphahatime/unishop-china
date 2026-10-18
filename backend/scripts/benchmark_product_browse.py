"""Guarded local MySQL browse benchmark with exact committed synthetic cleanup.

Run only on a disposable/local development server. The script refuses production,
keeps a before/after data fingerprint, and removes its own rows in a finally block.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import socket
from statistics import median
import subprocess
import sys
from time import perf_counter
import time
from uuid import uuid4

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.mysql import match
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.common.enums import UserRoleType
from app.core.config import settings
from app.core.database import engine
from app.models import Category, City, ProductListing, SellerVerification, User, UserProfile, UserRole
from app.models.seller_verification import VerificationStatus
from app.repositories.product_browse_repository import ProductBrowseRepository
from app.schemas.product_browse import BrowseQuery, BrowseSort
from app.services.product_browse_cursor import BrowsePosition
from scripts.audit_security_http import snapshot


def plan(connection, statement):
    compiled = statement.compile(dialect=engine.dialect)
    parameters = (tuple(compiled.params[name] for name in compiled.positiontup)
                  if compiled.positiontup is not None else compiled.params)
    raw = connection.exec_driver_sql("EXPLAIN FORMAT=JSON " + compiled.string, parameters).scalar_one()
    document = json.loads(raw)
    tables = []

    def visit(node):
        if isinstance(node, dict):
            if "table_name" in node:
                tables.append({key: node.get(key) for key in
                               ("table_name", "access_type", "key", "rows_examined_per_scan")})
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(document)
    return {"tables": tables, "filesort": "using_filesort" in raw}


def measure(db, query, position=None, *, repetitions=10):
    repo = ProductBrowseRepository()
    stmt = repo.page_statement(query, position)
    timings = []
    for _ in range(3):
        db.execute(stmt).mappings().all()
    for _ in range(repetitions):
        start = perf_counter()
        rows = db.execute(stmt).mappings().all()
        timings.append((perf_counter() - start) * 1000)
    timings.sort()
    return {"returned": len(rows), "query_count": 1,
            "min_ms": round(timings[0], 3), "max_ms": round(timings[-1], 3),
            "p50_ms": round(median(timings), 3),
            "p95_ms": round(timings[math.ceil(0.95 * len(timings)) - 1], 3),
            "p99_ms": round(timings[math.ceil(0.99 * len(timings)) - 1], 3),
            "plan": plan(db.connection(), stmt)}


def analyze(connection, statement):
    compiled = statement.compile(dialect=engine.dialect)
    parameters = (tuple(compiled.params[name] for name in compiled.positiontup)
                  if compiled.positiontup is not None else compiled.params)
    return connection.exec_driver_sql("EXPLAIN ANALYZE " + compiled.string, parameters).scalar_one()


def measure_live_http(query, *, warmups=3, repetitions=10):
    """Measure a real loopback HTTP request while synthetic rows still exist."""
    import httpx

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    backend_dir = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "error"],
        cwd=backend_dir,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    timings = []
    last_response = None
    try:
        with httpx.Client(timeout=15) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Benchmark Uvicorn process exited before readiness.")
                try:
                    health = client.get(base_url + "/api/v1/health/database")
                    if health.status_code == 200 and health.json().get("connected") is True:
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Benchmark Uvicorn did not become ready within 30 seconds.")

            params = {"q": query.q, "sort": query.sort.value, "limit": 25}
            for index in range(warmups + repetitions):
                started = perf_counter()
                response = client.get(base_url + "/api/v1/products", params=params)
                elapsed = (perf_counter() - started) * 1000
                if response.status_code != 200:
                    raise RuntimeError(f"Benchmark browse HTTP returned {response.status_code}.")
                if index >= warmups:
                    timings.append(elapsed)
                last_response = response
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    if last_response is None:
        raise RuntimeError("Benchmark HTTP request produced no response.")
    body = last_response.json()
    if len(body.get("items", [])) != 25:
        raise RuntimeError("Benchmark HTTP response did not return the expected 25-card page.")
    timings.sort()
    return {"transport": "real loopback HTTP to single-process Uvicorn",
            "warmup_runs": warmups, "measured_runs": repetitions,
            "returned": len(body["items"]), "response_bytes": len(last_response.content),
            "p50_ms": round(median(timings), 3),
            "p95_ms": round(timings[math.ceil(0.95 * len(timings)) - 1], 3),
            "p99_ms": round(timings[math.ceil(0.99 * len(timings)) - 1], 3),
            "min_ms": round(timings[0], 3), "max_ms": round(timings[-1], 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--allow-development-synthetic-writes", action="store_true")
    parser.add_argument("--analyze", action="store_true",
                        help="Include actual-row EXPLAIN ANALYZE for the common-term query.")
    parser.add_argument("--summary", action="store_true",
                        help="Print compact scenario timings instead of complete JSON plans.")
    parser.add_argument("--live-http", action="store_true",
                        help="Measure common-term browse through a real local Uvicorn HTTP server.")
    args = parser.parse_args()
    if (not args.allow_development_synthetic_writes or not 1000 <= args.rows <= 100000
            or settings.app_env.strip().lower() != "development"
            or engine.url.database != "unishop_china"
            or engine.url.host not in {"127.0.0.1", "localhost", "::1"}):
        parser.error("Refused: explicit local-development consent and 1,000–100,000 rows required.")

    before = snapshot(engine)
    marker = uuid4().hex
    user_id = category_id = rare_category_id = rare_city_id = None
    with Session(engine) as db:
        try:
            city = db.scalar(select(City).where(City.slug == "qingdao", City.is_active.is_(True)))
            if city is None:
                raise RuntimeError("Active benchmark city unavailable.")
            user = User(email=f"phase11b-benchmark-{marker}@example.invalid",
                        password_hash="synthetic-unusable", email_verified=True, phone_verified=True)
            db.add(user)
            db.flush()
            user_id = user.id
            db.add(UserRole(user_id=user_id, role=UserRoleType.BUYER))
            db.add(UserProfile(user_id=user_id, display_name="Synthetic Benchmark",
                               city=city.name_en, city_id=city.id, onboarding_completed=True))
            db.add(SellerVerification(user_id=user_id, status=VerificationStatus.VERIFIED,
                                      submitted_at=datetime.now(timezone.utc),
                                      reviewed_at=datetime.now(timezone.utc)))
            category = Category(slug="phase11b-bench-" + marker[:16],
                                name_en="Synthetic Benchmark", name_zh="基准测试")
            db.add(category)
            rare_category = Category(slug="phase11b-rare-" + marker[:16],
                                     name_en="Synthetic Rare", name_zh="稀有测试")
            db.add(rare_category)
            rare_city = City(slug="phase11b-rare-" + marker[:16],
                             name_en="Synthetic Rare", name_zh="稀有城市",
                             province_en="Synthetic", country_code="CN")
            db.add(rare_city)
            db.flush()
            category_id = category.id
            rare_category_id = rare_category.id
            rare_city_id = rare_city.id
            db.commit()

            now = datetime.now(timezone.utc)
            batch = []
            for index in range(args.rows):
                term = "bamboo" if index % 10 == 0 else "steel"
                batch.append({"id": str(uuid4()), "seller_user_id": user_id,
                              "public_slug": "item-" + uuid4().hex[:24],
                              "title": f"Synthetic {term} desk {index}",
                              "description": "Synthetic benchmark listing for bounded browse measurement.",
                              "price": Decimal(index % 100000 + 1) / Decimal(100),
                              "currency": "CNY", "condition": "good", "status": "PUBLISHED",
                              "city_id": city.id, "category_id": category_id,
                              "published_at": now, "created_at": now, "updated_at": now})
                if len(batch) == 1000:
                    db.execute(insert(ProductListing), batch)
                    db.commit()
                    batch.clear()
            if batch:
                db.execute(insert(ProductListing), batch)
                db.commit()
            db.add(ProductListing(seller_user_id=user_id, title="Synthetic zzqxv bamboo desk",
                description="Synthetic benchmark listing for bounded browse measurement.",
                price=Decimal("25.00"), currency="CNY", condition="good", status="PUBLISHED",
                city_id=city.id, category_id=rare_category_id, published_at=now))
            db.add(ProductListing(seller_user_id=user_id, title="Synthetic rare city desk",
                description="Synthetic benchmark listing for bounded browse measurement.",
                price=Decimal("25.00"), currency="CNY", condition="good", status="PUBLISHED",
                city_id=rare_city_id, category_id=category_id, published_at=now))
            db.commit()

            public_synthetic_count = db.scalar(select(func.count()).select_from(ProductListing).where(
                ProductListing.seller_user_id == user_id,
                ProductListing.status == "PUBLISHED"))
            hidden_synthetic_count = db.scalar(select(func.count()).select_from(ProductListing).where(
                ProductListing.seller_user_id == user_id,
                ProductListing.status != "PUBLISHED"))

            scenarios = {
                "newest": BrowseQuery(),
                "city": BrowseQuery(city=city.slug),
                "rare_city": BrowseQuery(city=rare_city.slug),
                "category": BrowseQuery(category=category.slug),
                "city_category": BrowseQuery(city=city.slug, category=category.slug),
                "rare_category": BrowseQuery(category=rare_category.slug),
                "price_range": BrowseQuery(min_price=Decimal("10.00"),
                                           max_price=Decimal("90.00")),
                "price_asc": BrowseQuery(sort=BrowseSort.PRICE_ASC),
                "price_desc": BrowseQuery(sort=BrowseSort.PRICE_DESC),
                "keyword": BrowseQuery(q="bamboo"),
                "selective_keyword": BrowseQuery(q="zzqxv"),
                "keyword_city": BrowseQuery(q="bamboo", city=city.slug),
                "keyword_category": BrowseQuery(q="bamboo", category=category.slug),
                "keyword_city_category": BrowseQuery(q="bamboo", city=city.slug,
                                                       category=category.slug),
                "combined": BrowseQuery(q="bamboo", city=city.slug, category=category.slug,
                                        min_price=Decimal("10.00"), sort=BrowseSort.PRICE_ASC),
            }
            results = {name: measure(db, query) for name, query in scenarios.items()}
            if args.analyze:
                results["keyword"]["explain_analyze"] = analyze(
                    db.connection(), ProductBrowseRepository().page_statement(scenarios["keyword"], None))
            raw_search = select(ProductListing.public_slug).where(match(
                ProductListing.title, ProductListing.description, against="bamboo",
                in_natural_language_mode=True)).limit(25)
            raw_timings = []
            for _ in range(10):
                start = perf_counter()
                db.execute(raw_search).all()
                raw_timings.append((perf_counter() - start) * 1000)
            results["raw_fulltext_25"] = {"p50_ms": round(median(raw_timings), 3),
                                          "plan": plan(db.connection(), raw_search)}
            phrase_search = select(ProductListing.public_slug).where(match(
                ProductListing.title, ProductListing.description, against='"bamboo"',
                in_boolean_mode=True)).limit(25)
            phrase_timings = []
            for _ in range(10):
                start = perf_counter()
                db.execute(phrase_search).all()
                phrase_timings.append((perf_counter() - start) * 1000)
            results["raw_phrase_25"] = {"p50_ms": round(median(phrase_timings), 3),
                                         "plan": plan(db.connection(), phrase_search)}
            boolean_term = select(ProductListing.public_slug).where(match(
                ProductListing.title, ProductListing.description, against="bamboo",
                in_boolean_mode=True)).limit(25)
            term_timings = []
            for _ in range(10):
                start = perf_counter()
                db.execute(boolean_term).all()
                term_timings.append((perf_counter() - start) * 1000)
            results["raw_boolean_25"] = {"p50_ms": round(median(term_timings), 3),
                                          "plan": plan(db.connection(), boolean_term)}
            for label, value, boolean in (("natural", "bamboo", False),
                                          ("boolean", "bamboo", True),
                                          ("phrase", '"bamboo"', True)):
                results[f"{label}_match_count"] = db.scalar(
                    select(func.count()).select_from(ProductListing).where(match(
                        ProductListing.title, ProductListing.description,
                        against=value, in_boolean_mode=boolean,
                        in_natural_language_mode=not boolean)))
            first = ProductBrowseRepository().page(db, scenarios["newest"], None)[23]
            results["cursor_page"] = measure(db, scenarios["newest"],
                BrowsePosition(first.published_at, first.public_slug))
            first_price = ProductBrowseRepository().page(db, scenarios["price_asc"], None)[23]
            results["price_cursor_page"] = measure(db, scenarios["price_asc"],
                BrowsePosition(first_price.price, first_price.public_slug))
            if args.live_http:
                results["live_http_keyword"] = measure_live_http(scenarios["keyword"])
            reported = results
            if args.summary:
                reported = {name: {key: value for key, value in result.items()
                                   if key != "plan"}
                            if isinstance(result, dict) else result
                            for name, result in results.items()}
            print(json.dumps({"rows": args.rows, "mysql_version": db.connection().exec_driver_sql(
                "SELECT VERSION()").scalar_one(),
                "dataset": {"generated_base_rows": args.rows,
                            "publicly_eligible_synthetic_listings": public_synthetic_count,
                            "hidden_synthetic_listings": hidden_synthetic_count},
                "scenarios": reported}, indent=2))
        finally:
            db.rollback()
            if user_id is not None:
                db.execute(delete(ProductListing).where(ProductListing.seller_user_id == user_id))
                if category_id is not None:
                    db.execute(delete(Category).where(Category.id == category_id))
                if rare_category_id is not None:
                    db.execute(delete(Category).where(Category.id == rare_category_id))
                if rare_city_id is not None:
                    db.execute(delete(City).where(City.id == rare_city_id))
                db.execute(delete(SellerVerification).where(SellerVerification.user_id == user_id))
                db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
                db.execute(delete(UserRole).where(UserRole.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
                db.commit()
    if snapshot(engine) != before:
        raise RuntimeError("Development data fingerprint changed after synthetic cleanup.")
    print("Synthetic rows removed; development data fingerprint unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
