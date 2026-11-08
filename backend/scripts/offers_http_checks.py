"""Focused real Uvicorn/MySQL offer smoke with exact synthetic cleanup."""
import argparse
import tempfile
from uuid import uuid4
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import engine
from app.models import Conversation, Message, WeChatShareRequest
from app.services.token_service import AccessTokenService
from scripts.chat_http_checks import start_server
from scripts.personalization_http_checks import database_fingerprint, stop_server
from tests.fixtures.offers import cleanup_offer_world, seed_offer_world


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-development-synthetic-writes", action="store_true", required=True)
    parser.parse_args()
    if settings.app_env != "development" or engine.url.database != "unishop_china":
        raise RuntimeError("Development-only synthetic check.")
    baseline = database_fingerprint()
    with Session(engine, expire_on_commit=False) as db, db.begin():
        world, refs = seed_offer_world(db)
    try:
        with tempfile.TemporaryDirectory(prefix="unishop-phase14-http-") as storage:
            process, url = start_server(storage)
            try:
                with httpx.Client(base_url=url, timeout=15, trust_env=False) as client:
                    def auth(user):
                        return {"Authorization": "Bearer "+AccessTokenService().create_access_token(user.id)}
                    def offer(index, actor):
                        return client.post("/api/v1/offers", headers=auth(actor), json={
                            "conversation_ref": refs[index], "amount": "55.50", "client_offer_id": str(uuid4())})
                    first = offer(0, world.buyer)
                    loser = offer(5, world.outsider)
                    assert first.status_code == loser.status_code == 201
                    assert first.headers["cache-control"] == "no-store"
                    path = "/api/v1/offers/"+first.json()["offer_ref"]
                    assert client.get(path, headers=auth(world.outsider)).status_code == 404
                    assert client.post(path+"/accept", headers=auth(world.buyer)).status_code == 403
                    body = {"amount": "60.00", "client_offer_id": str(uuid4())}
                    counter = client.post(path+"/counteroffers", headers=auth(world.seller), json=body)
                    assert counter.status_code == 201
                    accept = "/api/v1/offers/"+counter.json()["offer_ref"]+"/accept"
                    deal = client.post(accept, headers=auth(world.buyer))
                    assert deal.status_code == 200 and deal.json()["amount"] == "60.00"
                    assert client.post(accept, headers=auth(world.buyer)).json() == deal.json()
                    assert client.post(path+"/counteroffers", headers=auth(world.seller), json=body).status_code == 200
                    assert client.get("/api/v1/products/"+world.products[0].public_slug).status_code == 404
                    cancelled = client.get("/api/v1/offers/"+loser.json()["offer_ref"], headers=auth(world.outsider)).json()
                    assert cancelled["status"] == "CANCELLED" and cancelled["deal_ref"] is None
                    assert client.get("/api/v1/deals/"+deal.json()["deal_ref"], headers=auth(world.outsider)).status_code == 404
                    assert client.get("/api/v1/chat/conversations/"+refs[0], headers=auth(world.buyer)).status_code == 200
                    assert client.get("/api/v1/offers", headers=auth(world.buyer)).status_code == 200
                    assert client.get("/api/v1/deals", headers=auth(world.buyer)).status_code == 200
                    for private in (world.buyer.id, world.seller.id, world.buyer.email, "contact_ciphertext", "storage_key"):
                        assert private not in deal.text and private not in first.text
                with Session(engine) as db:
                    scope = select(Conversation.id).where(Conversation.product_listing_id.in_([p.id for p in world.products]))
                    assert db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id.in_(scope))) == 0
                    assert db.scalar(select(func.count()).select_from(WeChatShareRequest).where(WeChatShareRequest.conversation_id.in_(scope))) == 0
            finally:
                stop_server(process)
    finally:
        with Session(engine) as db, db.begin():
            cleanup_offer_world(db, world)
        assert database_fingerprint() == baseline, "Synthetic HTTP cleanup changed pre-existing data."
    print("PASS real Uvicorn/MySQL: create, counter, accept, replay, archive, competing cancellation, BOLA, roles, chat, privacy, no automatic messages/contact, exact cleanup")


if __name__ == "__main__":
    main()
