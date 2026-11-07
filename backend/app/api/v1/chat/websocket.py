"""Authentication-first WebSocket transport; services own all database policy."""
import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.common.chat import ChatError
from app.core.config import allowed_frontend_origins
from app.core.database import SessionLocal
from app.core.exceptions import TokenValidationError
from app.core.websocket_manager import ChatConnection, WebSocketConnectionManager
from app.schemas.chat_events import (
    MAX_EVENT_BYTES, AuthenticateEvent, PingEvent, SendMessageEvent, SubscribeEvent, parse_event,
)
from app.schemas.message import MessageResponse
from app.services.chat_service import ConversationService
from app.services.message_service import MessageService
from app.services.token_service import AccessTokenService

router = APIRouter()
WS_AUTH_TIMEOUT_SECONDS = 5
WS_IDLE_TIMEOUT_SECONDS = 60
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}


def _authorize(config, actor_id, reference=None):
    with SessionLocal() as db:
        service = ConversationService(db, config=config)
        if reference is None:
            service.authenticate(actor_id)
        else:
            service.authorize(actor_id, reference)


def _authenticate(config, raw_token):
    claims = AccessTokenService(config).decode_access_token(raw_token)
    _authorize(config, claims.subject)
    return claims


def _send(config, actor_id, event, expires_at):
    # Thread-pool queueing must not turn an expired connection into a new write.
    if expires_at <= time.time():
        raise ChatError("Authentication expired.", 401)
    with SessionLocal() as db:
        # Service returns after commit. No SQLAlchemy session crosses await.
        return MessageService(db, config=config).send(
            actor_id, event.conversation_ref, event.client_message_id, event.content)


def _message_payload(message):
    return MessageResponse.model_validate(message).model_dump(mode="json")


async def _deny(websocket, status=403):
    if "websocket.http.response" in websocket.scope.get("extensions", {}):
        response = JSONResponse(
            {"detail": "Connection unavailable."}, status_code=status, headers=PRIVATE_HEADERS)
        # Uvicorn's SansIO rejection generates Content-Length itself and appends
        # ASGI headers. Supplying it twice makes strict clients reject the 403.
        del response.headers["content-length"]
        await websocket.send_denial_response(response)
    else:
        await websocket.close(code=1008)


async def _receive(websocket, manager, connection, timeout):
    packet = await asyncio.wait_for(websocket.receive(), timeout)
    if packet["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(packet.get("code", 1000))
    if not manager.consume_frame(connection):
        await manager.close(connection, 1008)
        return None
    value = packet.get("text")
    if not isinstance(value, str):
        await manager.close(connection, 1003)
        return None
    if len(value.encode("utf-8")) > MAX_EVENT_BYTES:
        await manager.close(connection, 1009)
        return None
    return parse_event(value)


async def _operate(event, connection: ChatConnection, manager, config):
    if isinstance(event, AuthenticateEvent):
        await manager.close(connection, 1008)
    elif isinstance(event, SubscribeEvent):
        await run_in_threadpool(_authorize, config, connection.user_id, event.conversation_ref)
        if not manager.subscribe(connection, event.conversation_ref):
            await manager.close(connection, 1008)
            return
        await manager.enqueue(connection, {"v": 1, "type": "subscribed",
            "conversation_ref": event.conversation_ref}, event.conversation_ref)
    elif isinstance(event, SendMessageEvent):
        result = await run_in_threadpool(_send, config, connection.user_id, event, connection.expires_at)
        message = _message_payload(result.message)
        await manager.enqueue(connection, {"v": 1, "type": "message.ack",
            "message": message, "created": result.created}, event.conversation_ref)
        if result.created:
            await manager.publish(event.conversation_ref, {"v": 1, "type": "message.created", "message": message})
    elif isinstance(event, PingEvent):
        await run_in_threadpool(_authorize, config, connection.user_id)
        await manager.enqueue(connection, {"v": 1, "type": "pong"})


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    config = websocket.app.state.settings
    origins = websocket.headers.getlist("origin")
    if (len(origins) != 1 or origins[0] not in allowed_frontend_origins(config)
            or websocket.scope.get("query_string") or websocket.scope.get("subprotocols")
            or websocket.headers.get("authorization")):
        await _deny(websocket)
        return
    manager: WebSocketConnectionManager = websocket.app.state.chat_manager
    peer = websocket.client.host if websocket.client else "unknown"
    connection = manager.reserve(websocket, peer)
    if connection is None:
        await _deny(websocket, 429)
        return
    try:
        await websocket.accept(headers=[(key.lower().encode(), value.encode()) for key, value in PRIVATE_HEADERS.items()])
        async with asyncio.timeout(WS_AUTH_TIMEOUT_SECONDS):
            event = await _receive(websocket, manager, connection, WS_AUTH_TIMEOUT_SECONDS)
            if not isinstance(event, AuthenticateEvent):
                await manager.close(connection, 4401)
                return
            claims = await run_in_threadpool(_authenticate, config, event.access_token.get_secret_value())
            del event

            async def authorize(actor_id, reference):
                await run_in_threadpool(_authorize, config, actor_id, reference)

            if not manager.authenticate(connection, claims.subject, claims.expires_at.timestamp(), authorize):
                await manager.close(connection, 4401)
                return
        await manager.enqueue(connection, {"v": 1, "type": "authenticated"})
        while not connection.closed:
            event = await _receive(websocket, manager, connection, WS_IDLE_TIMEOUT_SECONDS)
            if event is None or connection.closed:
                break
            if connection.expires_at <= manager.now():
                await manager.close(connection, 4401)
                break
            try:
                await _operate(event, connection, manager, config)
            except ChatError as error:
                if error.status_code == 401:
                    await manager.close(connection, 4401)
                    break
                safe_codes = {400: "invalid_request", 422: "invalid_request", 403: "forbidden", 404: "not_found",
                              409: "conflict", 429: "rate_limited", 503: "unavailable"}
                await manager.enqueue(connection, {"v": 1, "type": "error",
                    "code": safe_codes.get(error.status_code, "unavailable")})
    except (TokenValidationError, ChatError):
        await manager.close(connection, 4401)
    except TimeoutError:
        await manager.close(connection, 1008)
    except WebSocketDisconnect:
        pass
    except (ValueError, TypeError, RecursionError):
        await manager.close(connection, 1008)
    except Exception:
        await manager.close(connection, 1011)
    finally:
        await manager.close(connection)
