"""Real MySQL conversation, history, consent and HTTP privacy invariants."""
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.common.chat import ChatError
from app.common.enums import AccountStatus
from app.core.chat_limits import clear_chat_limits
from app.core.database import get_db
from app.main import create_app
from app.models import Category, City, SellerVerification, UserProfile
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.wechat_share_request import WeChatShareRequest
from app.services.message_service import MessageService
from tests.fixtures.conversations import chat_config, seed_chat_world
from tests.integration.test_seller_verification import headers

BASE = "/api/v1/chat/conversations"
UNKNOWN = "cv-" + "f" * 32
CONTACT = "Synthetic_123"


@pytest.fixture
def chat_world(db_session):
    clear_chat_limits()
    config = chat_config()
    world = seed_chat_world(db_session, count=5)
    # Every chat regression runs beside unrelated synthetic history. This makes
    # global counts/updates and arbitrary consent-row selection fail visibly.
    other = seed_chat_world(db_session, count=1)
    sentinel = Conversation(buyer_user_id=other.buyer.id, seller_user_id=other.seller.id,
                            product_listing_id=other.products[0].id)
    db_session.add(sentinel)
    db_session.flush()
    sentinel_id = sentinel.id
    db_session.add(Message(conversation_id=sentinel_id, sender_user_id=other.buyer.id,
                           client_message_id=str(uuid4()), content="Unrelated synthetic history"))
    db_session.add(WeChatShareRequest(conversation_id=sentinel_id))
    db_session.commit()
    def sentinel_state():
        return tuple(db_session.execute(select(model.__table__).where(column == sentinel_id)).one()
                     for model, column in ((Conversation, Conversation.id),
                                           (Message, Message.conversation_id),
                                           (WeChatShareRequest, WeChatShareRequest.conversation_id)))
    baseline = sentinel_state()
    app = create_app(config)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db_session, world, config
    assert sentinel_state() == baseline, "Chat test changed unrelated history."
    clear_chat_limits()


def start(world, index=0, user=None):
    client, _, data, _ = world
    response = client.post(BASE, headers=headers(user or data.buyer),
                           json={"product_slug": data.products[index].public_slug})
    assert response.status_code == 200, response.text
    return response.json()["conversation_ref"]


def handoff(world, ref, action=None, *, user=None, body=None):
    client, _, data, _ = world
    path = f"{BASE}/{ref}/wechat"
    if action is None:
        return client.get(path, headers=headers(user or data.buyer))
    return client.post(path + "/" + action, headers=headers(user or data.buyer),
                       **({"json": body} if body is not None else {}))


def send(world, ref, content="Hello, is this available?", *, actor=None, client_id=None):
    _, db, data, config = world
    return MessageService(db, config=config).send((actor or data.buyer).id, ref,
                                          client_id or str(uuid4()), content)


@pytest.mark.parametrize("method,suffix,body", [
    ("POST", "", {"product_slug": "item-" + "a" * 24}), ("GET", "", None),
    ("GET", "/" + UNKNOWN, None), ("GET", "/" + UNKNOWN + "/messages", None),
    ("GET", "/" + UNKNOWN + "/wechat", None),
    ("POST", "/" + UNKNOWN + "/wechat/request", None),
    ("POST", "/" + UNKNOWN + "/wechat/approve", {"contact": CONTACT}),
    ("POST", "/" + UNKNOWN + "/wechat/deny", None),
    ("POST", "/" + UNKNOWN + "/wechat/revoke", None),
])
def test_all_http_operations_require_bearer_and_private_headers(chat_world, method, suffix, body):
    response = chat_world[0].request(method, BASE + suffix, **({"json": body} if body is not None else {}))
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_create_reuse_roles_and_minimal_projection(chat_world):
    client, db, world, _ = chat_world
    ref = start(chat_world)
    assert ref.startswith("cv-") and len(ref) == 35
    assert start(chat_world) == ref
    assert db.scalar(select(func.count()).select_from(Conversation).where(
        Conversation.buyer_user_id == world.buyer.id)) == 1
    for actor, role in ((world.buyer, "buyer"), (world.seller, "seller")):
        response = client.get(f"{BASE}/{ref}", headers=headers(actor))
        assert response.status_code == 200
        assert set(response.json()) == {"conversation_ref", "product_slug", "role", "created_at", "activity_at"}
        assert response.json()["role"].lower() == role
        for value in (world.buyer.id, world.seller.id, world.buyer.email, world.seller.email, "contact_ciphertext"):
            assert value not in response.text
        page = client.get(BASE, headers=headers(actor)).json()
        assert [item["conversation_ref"] for item in page["items"]] == [ref]
    assert client.get(BASE, headers=headers(world.outsider)).json()["items"] == []


@pytest.mark.parametrize("suffix,method,body", [
    ("", "GET", None), ("/messages", "GET", None), ("/wechat", "GET", None),
    ("/wechat/request", "POST", None), ("/wechat/approve", "POST", {"contact": CONTACT}),
    ("/wechat/deny", "POST", None), ("/wechat/revoke", "POST", None),
])
def test_nonparticipant_cannot_read_or_mutate(chat_world, suffix, method, body):
    client, _, world, _ = chat_world
    ref = start(chat_world)
    response = client.request(method, BASE + "/" + ref + suffix, headers=headers(world.outsider),
                              **({"json": body} if body is not None else {}))
    assert response.status_code == 404
    assert world.buyer.id not in response.text and CONTACT not in response.text


def test_client_cannot_select_buyer_or_seller(chat_world):
    client, _, world, _ = chat_world
    for extra in ({"buyer_user_id": world.outsider.id}, {"seller_user_id": world.outsider.id},
                  {"buyer_id": world.outsider.id}, {"status": "APPROVED"}):
        response = client.post(BASE, headers=headers(world.buyer),
                               json={"product_slug": world.products[0].public_slug, **extra})
        assert response.status_code == 422


@pytest.mark.parametrize("field", ["email_verified", "phone_verified"])
def test_new_conversation_requires_verified_buyer(chat_world, field):
    client, db, world, _ = chat_world
    setattr(world.buyer, field, False)
    db.commit()
    response = client.post(BASE, headers=headers(world.buyer), json={"product_slug": world.products[0].public_slug})
    assert response.status_code == 403


def test_cannot_start_conversation_with_self(chat_world):
    client, _, world, _ = chat_world
    response = client.post(BASE, headers=headers(world.seller), json={"product_slug": world.products[0].public_slug})
    assert response.status_code in {403, 409}


@pytest.mark.parametrize("state", ["DRAFT", "PAUSED", "ARCHIVED"])
def test_new_conversation_cannot_target_nonpublic_product(chat_world, state):
    client, db, world, _ = chat_world
    world.products[0].status = state
    if state == "DRAFT":
        world.products[0].published_at = None
    db.commit()
    response = client.post(BASE, headers=headers(world.buyer), json={"product_slug": world.products[0].public_slug})
    assert response.status_code == 404


@pytest.mark.parametrize("case", ["seller_status", "seller_verified", "seller_profile", "city", "category", "parent"])
def test_canonical_visibility_is_reused_for_new_conversations(chat_world, case):
    client, db, world, _ = chat_world
    if case == "seller_status":
        world.seller.account_status = AccountStatus.SUSPENDED
    elif case == "seller_verified":
        db.execute(update(SellerVerification).where(SellerVerification.user_id == world.seller.id).values(
            status="REJECTED", rejection_reason="Synthetic rejection"))
    elif case == "seller_profile":
        db.execute(update(UserProfile).where(UserProfile.user_id == world.seller.id).values(onboarding_completed=False))
    elif case == "city":
        db.execute(update(City).where(City.id == world.products[0].city_id).values(is_active=False))
    elif case == "category":
        world.category.is_active = False
    else:
        parent = Category(slug="chat-parent-" + uuid4().hex[:12], name_en="Parent", name_zh="父", is_active=False)
        db.add(parent)
        db.flush()
        world.category.parent_id = parent.id
        world.category.parent_level = 1
        world.category.level = 2
    db.commit()
    slug = world.products[0].public_slug
    assert client.get("/api/v1/products/" + slug).status_code == 404
    assert client.post(BASE, headers=headers(world.buyer), json={"product_slug": slug}).status_code == 404


@pytest.mark.parametrize("state", ["PAUSED", "ARCHIVED"])
def test_existing_history_and_messages_survive_product_unavailability(chat_world, state):
    client, db, world, _ = chat_world
    ref = start(chat_world)
    world.products[0].status = state
    db.commit()
    assert client.get(f"{BASE}/{ref}", headers=headers(world.buyer)).status_code == 200
    assert send(chat_world, ref).created is True
    assert client.get(f"{BASE}/{ref}/messages", headers=headers(world.seller)).status_code == 200


@pytest.mark.parametrize("status", [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED])
def test_inactive_actor_cannot_read_or_write(chat_world, status):
    client, db, world, _ = chat_world
    ref = start(chat_world)
    world.buyer.account_status = status
    db.commit()
    assert client.get(f"{BASE}/{ref}", headers=headers(world.buyer)).status_code == 401
    with pytest.raises(ChatError) as failure:
        send(chat_world, ref)
    assert failure.value.status_code == 401


def test_active_participant_keeps_history_but_cannot_message_inactive_counterpart(chat_world):
    client, db, world, _ = chat_world
    ref = start(chat_world)
    send(chat_world, ref)
    world.seller.account_status = AccountStatus.SUSPENDED
    db.commit()
    assert client.get(f"{BASE}/{ref}/messages", headers=headers(world.buyer)).status_code == 200
    with pytest.raises(ChatError):
        send(chat_world, ref)
    assert handoff(chat_world, ref, "request").status_code in {403, 409}


def test_message_idempotency_content_conflict_and_actor_isolation(chat_world):
    _, db, world, _ = chat_world
    ref = start(chat_world)
    client_id = str(uuid4())
    first = send(chat_world, ref, "你好 — مرحبا — Bonjour", client_id=client_id)
    repeated = send(chat_world, ref, "你好 — مرحبا — Bonjour", client_id=client_id)
    assert first.created and not repeated.created
    assert first.message == repeated.message
    with pytest.raises(ChatError) as conflict:
        send(chat_world, ref, "Changed content", client_id=client_id)
    assert conflict.value.status_code == 409
    seller = send(chat_world, ref, "Seller's own idempotency scope", actor=world.seller, client_id=client_id)
    assert seller.created and seller.message.message_ref != first.message.message_ref
    assert db.scalar(select(func.count()).select_from(Message).join(Conversation).where(
        Conversation.public_ref == ref)) == 2
    with pytest.raises(ChatError) as denied:
        send(chat_world, ref, actor=world.outsider)
    assert denied.value.status_code == 404


@pytest.mark.parametrize("content", ["", "   ", "\t\n", "\x00hello", "hello\r", "x\u202ey", "\u200d", "x" * 2001])
def test_service_rejects_invalid_plain_text_without_transport_bypass(chat_world, content):
    ref = start(chat_world)
    with pytest.raises(ChatError) as failure:
        send(chat_world, ref, content)
    assert failure.value.status_code == 422


def test_message_failure_rolls_back_without_partial_activity(chat_world, monkeypatch):
    _, db, world, config = chat_world
    ref = start(chat_world)
    conversation = db.scalar(select(Conversation).where(Conversation.public_ref == ref))
    original_activity = conversation.activity_at
    actor = world.buyer.id
    original_commit = db.commit
    def failed_commit():
        raise OperationalError(None, None, Exception("Synthetic database failure"))
    monkeypatch.setattr(db, "commit", failed_commit)
    with pytest.raises((OperationalError, ChatError)):
        MessageService(db, config=config).send(actor, ref, str(uuid4()), "Must never be persisted")
    monkeypatch.setattr(db, "commit", original_commit)
    assert db.scalar(select(func.count()).select_from(Message).join(Conversation).where(
        Conversation.public_ref == ref)) == 0
    assert db.scalar(select(Conversation.activity_at).where(Conversation.public_ref == ref)) == original_activity


def test_equal_timestamp_history_and_cursor_isolation(chat_world):
    client, db, world, _ = chat_world
    first, second = start(chat_world), start(chat_world, 1)
    expected = {send(chat_world, first, f"Message {index}").message.message_ref for index in range(5)}
    db.execute(update(Message).where(Message.public_ref.in_(expected)).values(
        created_at=datetime(2026, 1, 2, 3, 4, 5, 123456)))
    db.commit()
    path = f"{BASE}/{first}/messages"
    page = client.get(path, headers=headers(world.buyer), params={"limit": 2}).json()
    cursor = page["next_cursor"]
    assert cursor
    assert client.get(f"{BASE}/{second}/messages", headers=headers(world.buyer), params={"limit": 2, "cursor": cursor}).status_code == 400
    assert client.get(path, headers=headers(world.seller), params={"limit": 2, "cursor": cursor}).status_code == 400
    assert client.get(path, headers=headers(world.buyer), params={"limit": 3, "cursor": cursor}).status_code == 400
    seen = [item["message_ref"] for item in page["items"]]
    while cursor:
        page = client.get(path, headers=headers(world.buyer), params={"limit": 2, "cursor": cursor}).json()
        seen.extend(item["message_ref"] for item in page["items"])
        cursor = page["next_cursor"]
    assert len(seen) == len(set(seen)) == 5 and set(seen) == expected


def test_equal_timestamp_conversation_keyset_pages(chat_world):
    client, db, world, _ = chat_world
    refs = {start(chat_world, index) for index in range(5)}
    db.execute(update(Conversation).where(Conversation.public_ref.in_(refs)).values(
        activity_at=datetime(2026, 1, 2, 3, 4, 5, 123456)))
    db.commit()
    seen, cursor = [], None
    for _ in range(4):
        page = client.get(BASE, headers=headers(world.buyer), params={"limit": 2, **({"cursor": cursor} if cursor else {})}).json()
        seen.extend(item["conversation_ref"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert cursor is None and len(seen) == len(set(seen)) == 5 and set(seen) == refs


@pytest.mark.parametrize("limit", [1, 20, 50])
def test_history_query_count_bounded_and_get_read_only(chat_world, limit):
    client, db, world, _ = chat_world
    ref = start(chat_world)
    for index in range(4):
        send(chat_world, ref, f"Message {index}")
    statements = []
    connection = db.connection()
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().upper())
    event.listen(connection, "before_cursor_execute", capture)
    try:
        response = client.get(f"{BASE}/{ref}/messages", headers=headers(world.buyer), params={"limit": limit})
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert len([value for value in statements if value.startswith("SELECT")]) <= 8
    assert not any(value.startswith(("UPDATE", "INSERT", "DELETE")) for value in statements)


def test_wechat_explicit_consent_encrypted_at_rest_and_revoke(chat_world):
    client, db, world, _ = chat_world
    ref = start(chat_world)
    initial = handoff(chat_world, ref)
    assert initial.status_code == 200 and initial.json()["contact"] is None
    assert handoff(chat_world, ref, "request").status_code == 200
    assert handoff(chat_world, ref, "request").status_code == 200
    assert handoff(chat_world, ref, "approve", body={"contact": CONTACT}).status_code == 403
    approved = handoff(chat_world, ref, "approve", user=world.seller, body={"contact": CONTACT})
    assert approved.status_code == 200 and approved.json()["contact"] is None
    row = db.scalar(select(WeChatShareRequest).join(Conversation).where(Conversation.public_ref == ref))
    assert row.contact_ciphertext and CONTACT not in row.contact_ciphertext
    for actor in (world.buyer, world.seller):
        response = handoff(chat_world, ref, user=actor)
        assert response.status_code == 200 and response.json()["contact"] == CONTACT
        assert response.headers["cache-control"] == "no-store"
    assert CONTACT not in client.get(BASE, headers=headers(world.buyer)).text
    assert CONTACT not in client.get(f"{BASE}/{ref}", headers=headers(world.buyer)).text
    assert CONTACT not in client.get("/api/v1/products/" + world.products[0].public_slug).text
    assert handoff(chat_world, ref, "approve", user=world.seller, body={"contact": CONTACT}).status_code == 200
    assert handoff(chat_world, ref, "approve", user=world.seller, body={"contact": "Different_123"}).status_code == 409
    assert handoff(chat_world, ref, "revoke", user=world.seller).status_code == 200
    assert handoff(chat_world, ref, "revoke", user=world.seller).status_code == 200
    assert handoff(chat_world, ref).json()["contact"] is None
    db.expire_all()
    assert db.scalar(select(WeChatShareRequest.contact_ciphertext).join(Conversation).where(
        Conversation.public_ref == ref)) is None
    assert handoff(chat_world, ref, "request").status_code == 409
    assert handoff(chat_world, ref, "approve", user=world.seller, body={"contact": CONTACT}).status_code == 409


def test_denied_and_revoked_pending_requests_cannot_reopen(chat_world):
    _, _, world, _ = chat_world
    for index, action in enumerate(("deny", "revoke")):
        ref = start(chat_world, index)
        assert handoff(chat_world, ref, "request").status_code == 200
        assert handoff(chat_world, ref, action, user=world.seller).status_code == 200
        assert handoff(chat_world, ref).json()["contact"] is None
        assert handoff(chat_world, ref, "request").status_code == 409


@pytest.mark.parametrize("body", [{"contact": "Ab123"}, {"contact": "1invalid"}, {"contact": "https://example.test"}, {"contact": "a" * 21}, {"contact": CONTACT, "seller_id": "forged"}])
def test_wechat_contact_validation_and_no_echo(chat_world, body):
    _, _, world, _ = chat_world
    ref = start(chat_world)
    handoff(chat_world, ref, "request")
    response = handoff(chat_world, ref, "approve", user=world.seller, body=body)
    assert response.status_code == 422
    assert body["contact"] not in response.text


@pytest.mark.parametrize("params", [{"user_id": "forged"}, {"limit": 0}, {"limit": 51}, {"limit": "01"}, [("limit", "1"), ("limit", "2")]])
def test_strict_unknown_duplicate_and_bounded_queries(chat_world, params):
    client, _, world, _ = chat_world
    assert client.get(BASE, headers=headers(world.buyer), params=params).status_code == 422


def test_body_bounds_malformed_json_and_no_redundant_send_endpoint(chat_world):
    client, _, world, _ = chat_world
    ref = start(chat_world)
    auth = {**headers(world.buyer), "Content-Type": "application/json"}
    assert client.post(BASE, headers=auth, content=b"{").status_code == 422
    assert client.post(BASE, headers=auth, content=b"x" * 1025).status_code == 413
    assert client.post(BASE, headers=auth, content=b'{"product_slug":"a","product_slug":"b"}').status_code == 422
    assert client.get(BASE, headers=headers(world.buyer), params={"cursor": "x" * 513}).status_code == 422
    assert client.post(f"{BASE}/{ref}/messages", headers=headers(world.buyer)).status_code == 405


def test_foreign_key_and_conversation_uniqueness_guards(chat_world):
    _, db, world, _ = chat_world
    ref = start(chat_world)
    row = db.scalar(select(Conversation).where(Conversation.public_ref == ref))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(Conversation(buyer_user_id=world.buyer.id, seller_user_id=world.seller.id,
                            product_listing_id=world.products[0].id))
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(Message(conversation_id=row.id, sender_user_id=str(uuid4()),
                       client_message_id=str(uuid4()), content="Unknown sender"))
        db.flush()


def test_active_seller_can_withdraw_consent_for_inactive_buyer(chat_world):
    _, db, world, _ = chat_world
    ref = start(chat_world)
    assert handoff(chat_world, ref, "request").status_code == 200
    assert handoff(chat_world, ref, "approve", user=world.seller, body={"contact": CONTACT}).status_code == 200
    world.buyer.account_status = AccountStatus.SUSPENDED
    db.commit()
    assert handoff(chat_world, ref, "revoke", user=world.seller).status_code == 200
    row = db.scalar(select(WeChatShareRequest).join(Conversation).where(Conversation.public_ref == ref))
    assert row.status == "REVOKED" and row.contact_ciphertext is None
