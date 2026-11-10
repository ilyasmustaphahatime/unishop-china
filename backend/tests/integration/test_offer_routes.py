"""Real MySQL HTTP lifecycle, privacy and transaction regressions; rollback scoped."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import defer
from app.common.enums import AccountStatus
from app.core.database import get_db
from app.core.offer_limits import clear_offer_limits
from app.core.chat_limits import clear_chat_limits
from app.main import create_app
from app.models import Conversation, Deal, Offer, ProductListing, SellerVerification
from app.services.product_service import ProductService
from app.schemas.product import ProductUpdate
from tests.fixtures.conversations import chat_config
from tests.fixtures.offers import seed_offer_world
from tests.integration.test_seller_verification import headers

ROOT = "/api/v1/offers"


@pytest.fixture
def world(db_session):
    clear_offer_limits()
    clear_chat_limits()
    data, refs = seed_offer_world(db_session)
    db_session.commit()
    config = chat_config()
    app = create_app(config)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db_session, data, config, refs
    clear_offer_limits()
    clear_chat_limits()


def create(world, index=0, *, user=None, amount="25.50", key=None):
    client, _, data, _, refs = world
    body = dict(conversation_ref=refs[index], amount=amount, client_offer_id=key or str(uuid4()))
    return client.post(ROOT, headers=headers(user or data.buyer), json=body)


def action(world, ref, name, *, user=None, body=None):
    client, _, data, _, _ = world
    return client.post(f"{ROOT}/{ref}/{name}", headers=headers(user or data.seller),
                       **({"json": body} if body is not None else {}))


def offer(world, **kwargs):
    response = create(world, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("state", ["loaded", "expired", "deferred", "detached"])
@pytest.mark.parametrize("model,field,replacement", [
    (Offer, "amount", Decimal("99.99")),
    (Offer, "parent_offer_id", "forged-parent"),
    (Deal, "product_title_snapshot", "Changed agreement title"),
    (Deal, "product_condition_snapshot", "fair"),
])
def test_persisted_terms_remain_immutable_when_unloaded(world, state, model, field, replacement):
    client, db, data, _, _ = world
    first = offer(world)
    response = action(world, first["offer_ref"], "accept")
    assert response.status_code == 200
    agreement = response.json()
    ref = first["offer_ref"] if model is Offer else agreement["deal_ref"]
    column = getattr(model, field)
    row = db.scalar(select(model).where(model.public_ref == ref))
    original = getattr(row, field)
    auth = headers(data.seller)
    if state == "deferred":
        db.expunge(row)
        row = db.scalar(select(model).options(defer(column)).where(model.public_ref == ref))
    elif state in {"expired", "detached"}:
        db.expire(row, [field])
        if state == "detached":
            db.expunge(row)
    if state != "loaded":
        assert field not in row.__dict__
    with pytest.raises(ValueError, match="cannot be changed"):
        setattr(row, field, replacement)
    db.flush()
    assert db.scalar(select(column).where(model.public_ref == ref)) == original
    assert client.get("/api/v1/deals/" + agreement["deal_ref"], headers=auth).json() == agreement


def test_loaded_immutable_terms_allow_identical_assignment(world):
    _, db, _, _, _ = world
    first = offer(world)
    row = db.scalar(select(Offer).where(Offer.public_ref == first["offer_ref"]))
    row.amount = row.amount
    row.parent_offer_id = row.parent_offer_id
    db.flush()


def test_counter_acceptance_snapshots_competitors_replay_and_chat(world):
    client, db, data, _, refs = world
    first = offer(world)
    competitor = offer(world, index=5, user=data.outsider)
    counter_body = {"amount": "30.00", "client_offer_id": str(uuid4())}
    counter = action(world, first["offer_ref"], "counteroffers", body=counter_body)
    assert counter.status_code == 201, counter.text
    counter = counter.json()
    assert counter["parent_offer_ref"] == first["offer_ref"]
    assert action(world, first["offer_ref"], "counteroffers", body=counter_body).status_code == 200
    ProductService().update(db, data.seller.id, data.products[0].public_slug,
                           ProductUpdate(title="Current acceptance title", price="88.99"))
    result = action(world, counter["offer_ref"], "accept", user=data.buyer)
    assert result.status_code == 200, result.text
    deal = result.json()
    assert deal["amount"] == "30.00" and deal["product_title_snapshot"] == "Current acceptance title"
    assert action(world, counter["offer_ref"], "accept", user=data.buyer).json() == deal
    assert action(world, first["offer_ref"], "counteroffers", body=counter_body).status_code == 200
    original = client.get(ROOT + "/" + first["offer_ref"], headers=headers(data.buyer)).json()
    assert original["amount"] == "25.50" and original["status"] == "COUNTERED"
    losing = client.get(ROOT + "/" + competitor["offer_ref"], headers=headers(data.outsider)).json()
    assert losing["status"] == "CANCELLED" and losing["deal_ref"] is None
    assert deal["deal_ref"] not in str(losing) and "30.00" not in str(losing)
    assert db.scalar(select(func.count()).select_from(Deal).where(Deal.product_listing_id == data.products[0].id)) == 1
    db.refresh(data.products[0])
    assert data.products[0].status == "ARCHIVED"
    assert client.get("/api/v1/products/" + data.products[0].public_slug).status_code == 404
    assert client.get("/api/v1/chat/conversations/" + refs[0], headers=headers(data.buyer)).status_code == 200
    assert client.get("/api/v1/chat/conversations/" + refs[0] + "/wechat", headers=headers(data.buyer)).json()["status"] == "NONE"
    assert client.get("/api/v1/deals/" + deal["deal_ref"], headers=headers(data.outsider)).status_code == 404
    assert client.get("/api/v1/deals", headers=headers(data.buyer)).json()["items"][0] == deal


@pytest.mark.parametrize("terminal", ["reject", "withdraw", "accept", "counteroffers", "expired", "archive"])
def test_terminal_states_never_reopen(world, terminal):
    client, db, data, _, _ = world
    ref = offer(world)["offer_ref"]
    if terminal == "expired":
        at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
        db.execute(update(Offer).where(Offer.public_ref == ref).values(created_at=at, expires_at=at+timedelta(days=1)))
        db.commit()
    elif terminal == "archive":
        ProductService().transition(db, data.seller.id, data.products[0].public_slug, "archive")
    else:
        result = action(world, ref, terminal, user=data.buyer if terminal == "withdraw" else data.seller,
                        body={"amount": "26.00", "client_offer_id": str(uuid4())} if terminal == "counteroffers" else None)
        assert result.status_code in (200, 201), result.text
    for command, user in [("accept", data.seller), ("reject", data.seller), ("withdraw", data.buyer)]:
        response = action(world, ref, command, user=user)
        assert response.status_code == (200 if command == terminal else 409), response.text
    assert client.get(ROOT + "/" + ref, headers=headers(data.buyer)).json()["status"] != "PENDING"


@pytest.mark.parametrize("suffix,method", [("", "GET"), ("/accept", "POST"), ("/reject", "POST"), ("/withdraw", "POST"), ("/counteroffers", "POST")])
def test_nonparticipant_idor(world, suffix, method):
    client, _, data, _, _ = world
    ref = offer(world)["offer_ref"]
    kwargs = {"json": {"amount": "2.00", "client_offer_id": str(uuid4())}} if suffix == "/counteroffers" else {}
    result = client.request(method, ROOT + "/" + ref + suffix, headers=headers(data.outsider), **kwargs)
    assert result.status_code == 404
    assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("command,role", [("accept", "buyer"), ("reject", "buyer"), ("counteroffers", "buyer"), ("withdraw", "seller")])
def test_wrong_roles(world, command, role):
    ref = offer(world)["offer_ref"]
    data = world[2]
    result = action(world, ref, command, user=getattr(data, role),
                    body={"amount": "2.00", "client_offer_id": str(uuid4())} if command == "counteroffers" else None)
    assert result.status_code == 403


def test_initial_seller_self_and_owner_fields_rejected(world):
    client, _, data, _, refs = world
    assert create(world, user=data.seller).status_code == 403
    response = client.post("/api/v1/chat/conversations", headers=headers(data.seller),
                           json={"product_slug": data.products[0].public_slug})
    assert response.status_code == 409
    for field in ("seller_id", "buyer_id", "status", "proposer_role", "expires_at"):
        response = client.post(ROOT, headers=headers(data.buyer), json={
            "conversation_ref": refs[0], "amount": "2.00", "client_offer_id": str(uuid4()), field: "attacker"})
        assert response.status_code == 422 and "attacker" not in response.text


def test_idempotency_conflict_and_single_pending_slot(world):
    key = str(uuid4())
    first = offer(world, key=key)
    assert create(world, key=key).status_code == 200
    assert create(world, key=key, amount="26").status_code == 409
    assert create(world).status_code == 409
    assert action(world, first["offer_ref"], "withdraw", user=world[2].buyer).status_code == 200
    assert create(world, key=key).json()["status"] == "WITHDRAWN"
    assert create(world).status_code == 201


@pytest.mark.parametrize("which", ["buyer", "seller"])
@pytest.mark.parametrize("state", [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED])
def test_inactive_actor_and_counterparty(world, which, state):
    client, db, data, _, _ = world
    ref = offer(world)["offer_ref"]
    target = getattr(data, which)
    target.account_status = state
    db.commit()
    assert client.get(ROOT + "/" + ref, headers=headers(target)).status_code == 401
    active = data.buyer if which == "seller" else data.seller
    assert client.get(ROOT + "/" + ref, headers=headers(active)).status_code == 200
    if which == "buyer":
        assert action(world, ref, "accept").status_code == 409
        assert action(world, ref, "reject").status_code == 200
    else:
        assert action(world, ref, "counteroffers", user=data.buyer, body={"amount": "2", "client_offer_id": str(uuid4())}).status_code == 403
        assert action(world, ref, "withdraw", user=data.buyer).status_code == 200


@pytest.mark.parametrize("kind", ["paused", "archive", "verification", "email", "phone", "category", "profile"])
def test_current_visibility_blocks_new_commitments(world, kind):
    _, db, data, _, _ = world
    ref = offer(world)["offer_ref"]
    if kind in {"paused", "archive"}:
        ProductService().transition(db, data.seller.id, data.products[0].public_slug, "pause" if kind == "paused" else "archive")
    elif kind == "verification":
        from app.models.seller_verification import VerificationStatus
        row = db.scalar(select(SellerVerification).where(SellerVerification.user_id == data.seller.id))
        row.status, row.rejection_reason = VerificationStatus.REJECTED, "Synthetic revocation"
        db.commit()
    elif kind in {"email", "phone"}:
        setattr(data.buyer, kind + "_verified", False)
        db.commit()
    elif kind == "category":
        data.category.is_active = False
        db.commit()
    else:
        from app.models import UserProfile
        profile = db.scalar(select(UserProfile).where(UserProfile.user_id == data.seller.id))
        profile.onboarding_completed = False
        db.commit()
    assert action(world, ref, "accept").status_code == 409
    expected = 201 if kind in {"paused", "archive"} else 403 if kind in {"email", "phone"} else 409
    assert create(world, index=1).status_code == expected


def test_expiry_equality_read_only_filter_and_replacement(world, monkeypatch):
    client, db, data, _, _ = world
    first = offer(world)
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    at = future.replace(tzinfo=None)
    db.execute(update(Offer).where(Offer.public_ref == first["offer_ref"])
               .values(created_at=at-timedelta(days=1), expires_at=at))
    db.commit()
    monkeypatch.setattr("app.services.offer_service.utc_now", lambda: future)
    got = client.get(ROOT + "/" + first["offer_ref"], headers=headers(data.buyer))
    assert got.json()["status"] == "EXPIRED"
    assert db.scalar(select(Offer.status).where(Offer.public_ref == first["offer_ref"])) == "PENDING"
    assert action(world, first["offer_ref"], "accept").status_code == 409
    second = offer(world, index=1)
    pending = client.get(ROOT, headers=headers(data.buyer), params={"status": "PENDING", "limit": 1}).json()
    assert [r["offer_ref"] for r in pending["items"]] == [second["offer_ref"]]
    assert client.get(ROOT, headers=headers(data.buyer), params={"status": "EXPIRED"}).json()["items"][0]["offer_ref"] == first["offer_ref"]
    assert create(world).status_code == 201
    assert db.scalar(select(Offer.status).where(Offer.public_ref == first["offer_ref"])) == "EXPIRED"


def test_pagination_privacy_and_bounded_queries(world):
    client, db, data, _, refs = world
    created = [offer(world, index=i) for i in range(4)]
    at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(update(Offer).where(Offer.public_ref.in_([x["offer_ref"] for x in created])).values(created_at=at, expires_at=at+timedelta(days=1)))
    db.commit()
    page = client.get(ROOT, headers=headers(data.buyer), params={"limit": 2}).json()
    cursor = page["next_cursor"]
    second = client.get(ROOT, headers=headers(data.buyer), params={"limit": 2, "cursor": cursor}).json()
    assert len({r["offer_ref"] for r in page["items"] + second["items"]}) == 4
    for params, user in [({"limit": 1, "cursor": cursor}, data.buyer),
                         ({"limit": 2, "cursor": cursor, "role": "buyer"}, data.buyer),
                         ({"limit": 2, "cursor": cursor}, data.outsider)]:
        assert client.get(ROOT, headers=headers(user), params=params).status_code == 400
    assert client.get(ROOT, headers=headers(data.outsider), params={"conversation_ref": refs[0]}).status_code == 404
    for secret in (data.buyer.id, data.seller.id, data.buyer.email, "storage_key", "contact_ciphertext"):
        assert secret not in str(page)
    statements = []
    connection = db.connection()
    def capture(*args):
        statements.append(args[2])
    event.listen(connection, "before_cursor_execute", capture)
    try:
        result = client.get(ROOT, headers=headers(data.buyer), params={"limit": 50})
        assert result.status_code == 200
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert len(statements) <= 4


def test_commit_failure_rolls_back_entire_acceptance(world, monkeypatch):
    client, db, data, _, _ = world
    ref = offer(world)["offer_ref"]
    competing = offer(world, index=5, user=data.outsider)["offer_ref"]
    def fail():
        raise RuntimeError("sensitive-database-password")
    monkeypatch.setattr(db, "commit", fail)
    response = action(world, ref, "accept")
    assert response.status_code == 503 and "sensitive" not in response.text
    assert db.scalar(select(Offer.status).where(Offer.public_ref == ref)) == "PENDING"
    assert db.scalar(select(Offer.status).where(Offer.public_ref == competing)) == "PENDING"
    assert db.scalar(select(ProductListing.status).where(ProductListing.id == data.products[0].id)) == "PUBLISHED"
    assert db.scalar(select(func.count()).select_from(Deal).where(Deal.product_listing_id == data.products[0].id)) == 0


def test_database_pending_and_conversation_product_constraints(world):
    _, db, data, _, refs = world
    first = offer(world)
    row = db.scalar(select(Offer).where(Offer.public_ref == first["offer_ref"]))
    values = dict(conversation_id=row.conversation_id, product_listing_id=row.product_listing_id,
        proposer_role="BUYER", amount="2.00", currency="CNY", client_offer_id=str(uuid4()),
        status="PENDING", created_at=row.created_at, expires_at=row.expires_at)
    empty = db.scalar(select(Conversation.id).where(Conversation.public_ref == refs[1]))
    for changed, code, constraint in (
        ({}, 1062, "uq_offers_pending"),
        ({"conversation_id": empty}, 1452, "fk_offers_conversation_product"),
        ({"conversation_id": empty, "product_listing_id": data.products[1].id, "amount": "0"}, 3819, "ck_offers_money"),
        ({"conversation_id": empty, "product_listing_id": data.products[1].id, "proposer_role": "SELLER"}, 3819, "ck_offers_role"),
    ):
        with pytest.raises(DBAPIError) as caught:
            with db.begin_nested():
                db.add(Offer(**{**values, **changed}))
                db.flush()
        assert caught.value.orig.args[0] == code
        assert constraint in str(caught.value.orig)


def test_openapi_authentication_errors_and_response_fields(world):
    schema = world[0].get("/openapi.json").json()
    for path, item in schema["paths"].items():
        if not path.startswith(("/api/v1/offers", "/api/v1/deals")):
            continue
        for method, operation in item.items():
            assert operation["security"]
            assert {"401", "403", "404", "409", "422", "429", "503"} <= set(operation["responses"])
            response = world[0].request(method, path.replace("{offer_ref}", "of-"+"a"*32).replace("{deal_ref}", "dl-"+"a"*32),
                **({"json": {"conversation_ref": "cv-"+"a"*32, "amount": "1", "client_offer_id": str(uuid4())}}
                   if path == ROOT and method == "post" else
                   {"json": {"amount": "1", "client_offer_id": str(uuid4())}} if path.endswith("/counteroffers") else {}))
            assert response.status_code == 401
            assert response.headers["cache-control"] == "no-store"
    for name in ("OfferResponse", "DealResponse"):
        assert not ({"id", "buyer_user_id", "seller_user_id", "contact", "storage_key"} & set(schema["components"]["schemas"][name]["properties"]))


def test_alternating_chain_and_incompatible_parent_key(world):
    _, _, data, _, _ = world
    first = offer(world)
    second_key = str(uuid4())
    second = action(world, first["offer_ref"], "counteroffers", body={"amount": "30", "client_offer_id": second_key}).json()
    third = action(world, second["offer_ref"], "counteroffers", user=data.buyer,
                   body={"amount": "28", "client_offer_id": str(uuid4())}).json()
    assert third["proposer_role"] == "buyer" and third["parent_offer_ref"] == second["offer_ref"]
    assert action(world, third["offer_ref"], "counteroffers", body={"amount": "30", "client_offer_id": second_key}).status_code == 409
    accepted = action(world, third["offer_ref"], "accept")
    assert accepted.status_code == 200 and accepted.json()["amount"] == "28.00"


@pytest.mark.parametrize("query", ["limit=0", "limit=51", "limit=01", "limit=1&limit=2", "cursor=", "role=admin",
                                   "status=unknown", "buyer_id=secret", "conversation_ref=internal-id"])
def test_strict_queries_no_input_echo(world, query):
    response = world[0].get(ROOT+"?"+query, headers=headers(world[2].buyer))
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "secret" not in response.text and "internal-id" not in response.text


def test_invalid_auth_origin_headers_and_safe_logs(world, caplog):
    client, _, data, _, _ = world
    secret = "synthetic-secret-credential"
    cases = [({"Authorization": "Bearer "+secret}, 401),
             ({**headers(data.buyer), "Origin": "https://untrusted.example.test"}, 403),
             (list(headers(data.buyer).items()) * 2, 401)]
    for request_headers, expected in cases:
        response = client.get(ROOT, headers=request_headers)
        assert response.status_code == expected and secret not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert secret not in caplog.text and data.buyer.email not in caplog.text


def test_pause_resume_and_terminal_history_with_inactive_counterparty(world):
    client, db, data, _, _ = world
    first = offer(world)
    ProductService().transition(db, data.seller.id, data.products[0].public_slug, "pause")
    assert action(world, first["offer_ref"], "accept").status_code == 409
    ProductService().transition(db, data.seller.id, data.products[0].public_slug, "publish")
    deal = action(world, first["offer_ref"], "accept").json()
    data.seller.account_status = AccountStatus.SUSPENDED
    db.commit()
    assert client.get("/api/v1/deals/"+deal["deal_ref"], headers=headers(data.buyer)).status_code == 200
    assert client.get("/api/v1/deals/"+deal["deal_ref"], headers=headers(data.seller)).status_code == 401


def test_deal_keysets_scope_and_filters(world):
    client, _, data, _, refs = world
    expected = set()
    for index in range(3):
        item = offer(world, index=index)
        expected.add(action(world, item["offer_ref"], "accept").json()["deal_ref"])
    cursor, seen = None, set()
    for _ in range(3):
        params = {"limit": 1, "role": "buyer"}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/api/v1/deals", headers=headers(data.buyer), params=params).json()
        seen.add(page["items"][0]["deal_ref"])
        cursor = page["next_cursor"]
        if cursor:
            assert client.get("/api/v1/deals", headers=headers(data.outsider), params={**params, "cursor": cursor}).status_code == 400
            assert client.get(ROOT, headers=headers(data.buyer), params={**params, "cursor": cursor}).status_code == 400
    assert seen == expected and cursor is None
    response = client.get("/api/v1/deals", headers=headers(data.buyer), params={"conversation_ref": refs[0]})
    assert len(response.json()["items"]) == 1
    assert client.get("/api/v1/deals", headers=headers(data.outsider)).json()["items"] == []


@pytest.mark.parametrize("kind", ["offers", "filtered", "deals"])
def test_query_plan_starts_with_indexed_membership_not_global_history(world, kind):
    from app.repositories.offer_repository import page_candidates
    from app.schemas.offer import OfferListQuery, DealListQuery
    _, db, data, _, refs = world
    convs = list(db.scalars(select(Conversation).where(Conversation.public_ref.in_(refs))))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(300):
        conv = convs[i % len(convs)]
        at = now - timedelta(minutes=i+2)
        db.add(Offer(conversation_id=conv.id, product_listing_id=conv.product_listing_id,
            proposer_role="BUYER", amount="1.25", currency="CNY", client_offer_id=str(uuid4()), status="WITHDRAWN",
            created_at=at, expires_at=at+timedelta(days=1), closed_at=at+timedelta(seconds=1), closed_by_role="BUYER"))
    db.flush()
    model, column, query = ((Deal, Deal.agreed_at, DealListQuery()) if kind == "deals" else
        (Offer, Offer.created_at, OfferListQuery(status="WITHDRAWN" if kind == "filtered" else None)))
    stmt = select(page_candidates(model, column, data.buyer.id, query, None, now))
    sql = str(stmt.compile(dialect=db.bind.dialect, compile_kwargs={"literal_binds": True}))
    plan = json.loads(db.connection().exec_driver_sql("EXPLAIN FORMAT=JSON "+sql).scalar())
    tables = []
    def walk(value):
        if isinstance(value, dict):
            if value.get("table_name") in {"offers", "deals", "conversations"}:
                tables.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(plan)
    assert len(tables) == (6 if kind == "deals" else 4)
    assert all(table["access_type"] in {"ref", "eq_ref", "const"} for table in tables)
    assert all(table["key"].startswith("ix_conversations_") for table in tables if table["table_name"] == "conversations")
