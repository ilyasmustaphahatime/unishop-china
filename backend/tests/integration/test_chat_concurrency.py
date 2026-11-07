"""Independent real MySQL transactions challenge chat uniqueness and consent races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.chat import ChatError
from app.core.chat_limits import clear_chat_limits
from app.core.database import engine
from app.integrations.wechat_cipher import WeChatCipher
from app.models import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.wechat_share_request import WeChatShareRequest
from app.services.chat_service import ConversationService
from app.services.message_service import MessageService
from app.services.wechat_service import WeChatHandoffService
from scripts.personalization_http_checks import database_fingerprint
from tests.fixtures.conversations import chat_config, cleanup_chat_world, seed_chat_world


@pytest.fixture
def committed_world():
    clear_chat_limits()
    baseline = database_fingerprint()
    config = chat_config()
    with Session(engine, expire_on_commit=False) as db, db.begin():
        world = seed_chat_world(db)
    try:
        yield world, config
    finally:
        with Session(engine) as db, db.begin():
            cleanup_chat_world(db, world)
        clear_chat_limits()
        assert database_fingerprint() == baseline, "Chat race synthetic cleanup must preserve every stored value."


def race(actor_id, operations):
    barrier = Barrier(len(operations))
    def run(operation):
        with Session(engine) as db:
            # Authentication may already have established a repeatable-read snapshot.
            db.scalar(select(User.id).where(User.id == actor_id))
            barrier.wait(timeout=15)
            try:
                return operation(db)
            except ChatError as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(run, operation) for operation in operations]
        return [future.result(timeout=30) for future in futures]


def create(world, config):
    with Session(engine) as db:
        return ConversationService(db, config=config).create(world.buyer.id, world.products[0].public_slug).conversation_ref


def handoff_service(db, config):
    return WeChatHandoffService(db, cipher=WeChatCipher(config), config=config)


def test_concurrent_conversation_creation_reuses_one_public_identity(committed_world):
    world, config = committed_world
    results = race(world.buyer.id, [lambda db: ConversationService(db, config=config).create(
        world.buyer.id, world.products[0].public_slug)] * 5)
    assert all(not isinstance(result, int) for result in results)
    assert len({result.conversation_ref for result in results}) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Conversation).where(Conversation.buyer_user_id == world.buyer.id)) == 1


def test_concurrent_identical_message_retries_commit_once(committed_world):
    world, config = committed_world
    ref = create(world, config)
    client_id = str(uuid4())
    results = race(world.buyer.id, [lambda db: MessageService(db, config=config).send(
        world.buyer.id, ref, client_id, "Identical concurrent content")] * 5)
    assert all(not isinstance(result, int) for result in results)
    assert sum(result.created for result in results) == 1
    assert len({result.message.message_ref for result in results}) == 1
    assert len({result.message.created_at for result in results}) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Message).where(Message.client_message_id == client_id)) == 1


def test_concurrent_conflicting_message_retries_have_one_winner(committed_world):
    world, config = committed_world
    ref = create(world, config)
    client_id = str(uuid4())
    results = race(world.buyer.id, [lambda db, content=content: MessageService(db, config=config).send(
        world.buyer.id, ref, client_id, content) for content in ("First content", "Different content")])
    assert results.count(409) == 1
    winner = next(result for result in results if not isinstance(result, int))
    assert winner.created
    with Session(engine) as db:
        row = db.scalar(select(Message).where(Message.client_message_id == client_id))
        assert row.content == winner.message.content


def test_concurrent_approve_and_revoke_cannot_restore_contact(committed_world):
    world, config = committed_world
    ref = create(world, config)
    with Session(engine) as db:
        handoff_service(db, config).request(world.buyer.id, ref)
    results = race(world.seller.id, [
        lambda db: handoff_service(db, config).approve(world.seller.id, ref, "Synthetic_123"),
        lambda db: handoff_service(db, config).revoke(world.seller.id, ref),
    ])
    assert not isinstance(results[1], int)
    assert not isinstance(results[0], int) or results[0] == 409
    with Session(engine) as db:
        result = handoff_service(db, config).get(world.buyer.id, ref)
        assert result.status == "REVOKED" and result.contact is None
        row = db.scalar(select(WeChatShareRequest).join(Conversation).where(Conversation.public_ref == ref))
        assert row.contact_ciphertext is None


def test_concurrent_different_approvals_do_not_replace_approved_contact(committed_world):
    world, config = committed_world
    ref = create(world, config)
    with Session(engine) as db:
        handoff_service(db, config).request(world.buyer.id, ref)
    results = race(world.seller.id, [lambda db, contact=contact: handoff_service(db, config).approve(
        world.seller.id, ref, contact) for contact in ("Synthetic_123", "Different_123")])
    assert results.count(409) == 1
    with Session(engine) as db:
        result = handoff_service(db, config).get(world.buyer.id, ref)
        assert result.status == "APPROVED" and result.contact in {"Synthetic_123", "Different_123"}


def test_concurrent_request_and_deny_remains_terminal(committed_world):
    world, config = committed_world
    ref = create(world, config)
    with Session(engine) as db:
        handoff_service(db, config).request(world.buyer.id, ref)
    results = race(world.buyer.id, [
        lambda db: handoff_service(db, config).request(world.buyer.id, ref),
        lambda db: handoff_service(db, config).deny(world.seller.id, ref),
    ])
    assert not isinstance(results[1], int)
    assert not isinstance(results[0], int) or results[0] == 409
    with Session(engine) as db:
        result = handoff_service(db, config).get(world.buyer.id, ref)
        assert result.status == "DENIED" and result.contact is None
