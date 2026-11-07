"""Guarded real Uvicorn/MySQL HTTP+WebSocket checks with exact synthetic cleanup.

Run ``python -m scripts.chat_http_checks --allow-development-synthetic-writes``.
Credentials, message payloads and contact values are never printed. Generated
contact/cursor keys exist only in the child process environment. No .env edits.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
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
from sqlalchemy import delete, func, select, update
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from app.core.config import settings
from app.core.database import engine
from app.models import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.wechat_share_request import WeChatShareRequest
from app.services.token_service import AccessTokenService
from scripts.personalization_http_checks import database_fingerprint, seed, cleanup, stop_server

BACKEND = Path(__file__).resolve().parents[1]
BASE = "/api/v1/chat/conversations"
ORIGIN = "http://localhost:5173"


class Checks:
    def __init__(self):
        self.labels = []

    def require(self, condition, label):
        if not condition:
            raise AssertionError(label)
        self.labels.append(label)


def start_server(storage):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = os.environ.copy()
    env.update({"APP_ENV": "development", "APP_DEBUG": "false", "FRONTEND_URL": ORIGIN,
        "BROWSE_CURSOR_SIGNING_KEY": secrets.token_urlsafe(48),
        "WECHAT_CONTACT_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "SELLER_PRIVATE_STORAGE_DIR": str(Path(storage) / "seller"),
        "PRODUCT_IMAGE_STORAGE_DIR": str(Path(storage) / "products"),
        "PRODUCT_IMAGE_STORAGE_PROVIDER": "local"})
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
        "--port", str(port), "--no-access-log", "--no-proxy-headers", "--ws", "websockets-sansio",
        "--ws-max-size", "16384", "--ws-per-message-deflate", "false"],
        cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=url, timeout=2, trust_env=False) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Synthetic server unavailable.")
                try:
                    if client.get("/api/v1/health/database").status_code == 200:
                        return process, url
                except httpx.TransportError:
                    pass
                time.sleep(.1)
        raise RuntimeError("Synthetic server readiness timeout.")
    except Exception:
        stop_server(process)
        raise


def event(ws, kind, checks, label):
    result = json.loads(ws.recv(timeout=8))
    checks.require(result.get("v") == 1 and result.get("type") == kind, label)
    return result


def authenticate(ws, token, checks):
    ws.send(json.dumps({"v": 1, "type": "authenticate", "access_token": token}))
    event(ws, "authenticated", checks, "socket-authenticated")


def closed(ws, checks, label, allowed_codes):
    try:
        ws.recv(timeout=8)
    except ConnectionClosed as error:
        code = error.rcvd.code if error.rcvd is not None else None
        checks.require(code in allowed_codes, label)
    else:
        raise AssertionError(label)


def socket_connect(url, **kwargs):
    return connect(url, open_timeout=5, close_timeout=3, proxy=None, **kwargs)


def run_checks(url, ids, password, checks):
    socket_url = url.replace("http://", "ws://") + "/api/v1/chat/ws"
    with httpx.Client(base_url=url, timeout=15, trust_env=False) as buyer, \
            httpx.Client(base_url=url, timeout=15, trust_env=False) as seller, \
            httpx.Client(base_url=url, timeout=15, trust_env=False) as outsider:
        tokens = []
        for client, index in ((seller, 0), (buyer, 1), (outsider, 2)):
            response = client.post("/api/v1/auth/login", json={"identifier": ids["emails"][index], "password": password})
            checks.require(response.status_code == 200, "real-login")
            token = response.json()["access_token"]
            tokens.append(token)
            client.headers["Authorization"] = "Bearer " + token
        seller_token, buyer_token, outsider_token = tokens
        response = buyer.post(BASE, json={"product_slug": ids["slugs"][0]})
        checks.require(response.status_code == 200, "conversation-created")
        reference = response.json()["conversation_ref"]
        checks.require(buyer.post(BASE, json={"product_slug": ids["slugs"][0]}).json()["conversation_ref"] == reference,
                       "conversation-idempotent")
        checks.require(outsider.get(BASE + "/" + reference).status_code == 404, "http-bola")
        checks.require(response.headers.get("cache-control") == "no-store" and
                       response.headers.get("pragma") == "no-cache", "private-cache")
        with socket_connect(socket_url, origin=ORIGIN) as first, socket_connect(socket_url, origin=ORIGIN) as second, \
                socket_connect(socket_url, origin=ORIGIN) as third:
            for ws, token in ((first, buyer_token), (second, seller_token), (third, outsider_token)):
                authenticate(ws, token, checks)
            for ws in (first, second):
                ws.send(json.dumps({"v": 1, "type": "subscribe", "conversation_ref": reference}))
                event(ws, "subscribed", checks, "participant-subscription")
            third.send(json.dumps({"v": 1, "type": "subscribe", "conversation_ref": reference}))
            checks.require(event(third, "error", checks, "cross-user-subscription-error")["code"] == "not_found",
                           "cross-user-subscription-denied")
            client_id = str(uuid4())
            payload = {"v": 1, "type": "message.send", "conversation_ref": reference,
                       "client_message_id": client_id, "content": "Synthetic hello 你好 مرحبا"}
            first.send(json.dumps(payload))
            acknowledgment = event(first, "message.ack", checks, "message-ack")
            checks.require(acknowledgment["created"] is True, "first-send-created")
            outgoing = event(first, "message.created", checks, "sender-notification")
            incoming = event(second, "message.created", checks, "recipient-notification")
            checks.require(incoming == outgoing, "same-authorized-notification")
            with engine.connect() as db:
                checks.require(db.scalar(select(Message.public_ref).where(Message.public_ref == incoming["message"]["message_ref"])) is not None,
                               "notification-is-already-committed")
            first.send(json.dumps(payload))
            checks.require(event(first, "message.ack", checks, "retry-ack")["created"] is False, "retry-idempotent")
            first.send(json.dumps({**payload, "content": "Conflicting synthetic content"}))
            checks.require(event(first, "error", checks, "conflict-error")["code"] == "conflict", "retry-conflict")
            third.send(json.dumps({"v": 1, "type": "ping"}))
            event(third, "pong", checks, "no-cross-conversation-delivery")
        history = seller.get(BASE + "/" + reference + "/messages")
        checks.require(history.status_code == 200 and len(history.json()["items"]) == 1, "offline-http-recovery")
        checks.require(history.json()["items"][0]["client_message_id"] == client_id, "durable-idempotency")
        path = BASE + "/" + reference + "/wechat"
        checks.require(buyer.post(path + "/request").status_code == 200, "handoff-request")
        checks.require(buyer.post(path + "/approve", json={"contact": "Synthetic_123"}).status_code == 403, "buyer-cannot-approve")
        approved = seller.post(path + "/approve", json={"contact": "Synthetic_123"})
        checks.require(approved.status_code == 200 and approved.json()["contact"] is None, "approval-status-only")
        checks.require(buyer.get(path).json()["contact"] == "Synthetic_123", "explicit-private-contact-read")
        with engine.connect() as db:
            encrypted = db.scalar(select(WeChatShareRequest.contact_ciphertext).join(Conversation).where(Conversation.public_ref == reference))
            checks.require(encrypted and "Synthetic_123" not in encrypted, "authenticated-encryption-at-rest")
        checks.require("Synthetic_123" not in buyer.get(BASE).text, "no-contact-list-leak")
        checks.require(seller.post(path + "/revoke").status_code == 200 and buyer.get(path).json()["contact"] is None,
                       "revocation-prevents-future-read")
        checks.require(buyer.post(path + "/request").status_code == 409, "revoked-consent-terminal")
        for options in ({}, {"origin": "https://untrusted.example"}, {"origin": ORIGIN, "additional_headers": {"Authorization": "Bearer forbidden"}}):
            try:
                with socket_connect(socket_url, **options):
                    raise AssertionError("untrusted-handshake-accepted")
            except InvalidStatus as error:
                checks.require(error.response.status_code == 403, "untrusted-handshake-denied")
        try:
            with socket_connect(socket_url + "?token=forbidden", origin=ORIGIN):
                raise AssertionError("url-token-accepted")
        except InvalidStatus as error:
            checks.require(error.response.status_code == 403, "url-token-rejected")
        expired = AccessTokenService(now_provider=lambda: datetime.now(timezone.utc) - timedelta(days=1)).create_access_token(ids["users"][1])
        for token in ("invalid", expired, buyer.cookies.get(settings.refresh_cookie_name)):
            with socket_connect(socket_url, origin=ORIGIN) as ws:
                ws.send(json.dumps({"v": 1, "type": "authenticate", "access_token": token}))
                closed(ws, checks, "invalid-expired-wrong-type-denied", {4401})
        with socket_connect(socket_url, origin=ORIGIN) as ws:
            closed(ws, checks, "authentication-deadline", {1008})
        with socket_connect(socket_url, origin=ORIGIN) as ws:
            authenticate(ws, buyer_token, checks)
            ws.send(b"unsupported binary")
            closed(ws, checks, "binary-frame-rejected", {1003})
        with socket_connect(socket_url, origin=ORIGIN) as ws:
            authenticate(ws, buyer_token, checks)
            ws.send("x" * 16385)
            closed(ws, checks, "oversized-frame-rejected", {1009})
        with socket_connect(socket_url, origin=ORIGIN) as ws:
            authenticate(ws, buyer_token, checks)
            ws.send(json.dumps({"v": 1, "type": "message.send", "conversation_ref": reference,
                               "client_message_id": str(uuid4()), "content": "Forged", "sender_id": ids["users"][0]}))
            closed(ws, checks, "sender-impersonation-rejected", {1008})
        service = AccessTokenService()
        short_token = AccessTokenService(now_provider=lambda: datetime.now(timezone.utc) - timedelta(
            seconds=service.expires_in_seconds - 3)).create_access_token(ids["users"][1])
        with socket_connect(socket_url, origin=ORIGIN) as ws:
            authenticate(ws, short_token, checks)
            closed(ws, checks, "live-token-expiry", {4401})
        with socket_connect(socket_url, origin=ORIGIN) as ws:
            authenticate(ws, buyer_token, checks)
            with engine.begin() as db:
                db.execute(update(User).where(User.id == ids["users"][1]).values(account_status="SUSPENDED"))
            ws.send(json.dumps({"v": 1, "type": "ping"}))
            closed(ws, checks, "live-account-suspension", {4401, 1008})
        with engine.begin() as db:
            db.execute(update(User).where(User.id == ids["users"][1]).values(account_status="ACTIVE"))
        with socket_connect(socket_url, origin=ORIGIN) as ws:
            authenticate(ws, outsider_token, checks)
            limited = False
            for _ in range(125):
                ws.send(json.dumps({"v": 1, "type": "ping"}))
                try:
                    packet = json.loads(ws.recv(timeout=8))
                    checks.require(packet["type"] == "pong", "pre-limit-pong")
                except ConnectionClosed as error:
                    checks.require(error.rcvd is not None and error.rcvd.code == 1008, "live-frame-rate-limit")
                    limited = True
                    break
            checks.require(limited, "frame-rate-limit-enforced")
        with engine.connect() as db:
            checks.require(db.scalar(select(func.count()).select_from(Message).join(Conversation).where(
                Conversation.public_ref == reference)) == 1, "rejected-events-never-persist")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-development-synthetic-writes", action="store_true")
    args = parser.parse_args()
    if (not args.allow_development_synthetic_writes or settings.app_env.lower() != "development"
            or engine.url.host not in {"127.0.0.1", "localhost", "::1"}
            or engine.url.database != "unishop_china"):
        parser.error("Explicit local-development synthetic-write consent is required.")
    baseline = database_fingerprint()
    checks, ids, process = Checks(), None, None
    result = 1
    with tempfile.TemporaryDirectory(prefix="unishop-chat-http-") as storage:
        try:
            password = secrets.token_urlsafe(32) + "Aa1"
            ids = seed(uuid4().hex, password)
            with engine.begin() as db:
                db.execute(update(User).where(User.id.in_(ids["users"])).values(email_verified=True, phone_verified=True))
            process, url = start_server(storage)
            run_checks(url, ids, password, checks)
            result = 0
        except Exception as error:
            print(json.dumps({"status": "FAIL", "error_type": type(error).__name__,
                              "failed_check": str(error) if isinstance(error, AssertionError) else None}))
        finally:
            if process is not None:
                stop_server(process)
            if ids is not None:
                with engine.begin() as db:
                    db.execute(delete(Conversation).where(Conversation.product_listing_id.in_(ids["products"]),
                                                          Conversation.seller_user_id == ids["users"][0]))
                cleanup(ids)
            preserved = database_fingerprint() == baseline
            media_clean = not any(path.is_file() for path in Path(storage).rglob("*"))
            print(json.dumps({"checks_passed": len(checks.labels), "labels": checks.labels,
                "data_preserved": preserved, "synthetic_cleanup": preserved, "media_clean": media_clean,
                "server_stopped": process is None or process.poll() is not None}))
            if not preserved or not media_clean:
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
