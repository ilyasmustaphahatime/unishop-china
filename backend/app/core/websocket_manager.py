"""Bounded single-process delivery; durable history belongs exclusively to MySQL."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import time
from typing import Any

from fastapi import WebSocket

from app.core.rate_limit import InMemoryRateLimiter

Authorize = Callable[[str, str | None], Awaitable[None]]


@dataclass(eq=False, slots=True)
class ChatConnection:
    websocket: WebSocket
    peer: str
    queue: asyncio.Queue
    user_id: str | None = None
    expires_at: float = 0
    authorize: Authorize | None = None
    subscriptions: set[str] = field(default_factory=set)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    writer: asyncio.Task | None = None
    expiry: asyncio.Task | None = None
    closed: bool = False


class WebSocketConnectionManager:
    """Collection mutations are synchronous on the owning application's event loop."""

    def __init__(self, *, max_connections=200, max_connections_per_peer=20,
                 max_connections_per_user=5, max_subscriptions=20, max_queue=32,
                 send_timeout=5.0, now_provider=time.time):
        self.max_connections = max_connections
        self.max_connections_per_peer = max_connections_per_peer
        self.max_connections_per_user = max_connections_per_user
        self.max_subscriptions = max_subscriptions
        self.max_queue = max_queue
        self.send_timeout = send_timeout
        self.now = now_provider
        self.connections: set[ChatConnection] = set()
        self.connect_budget = InMemoryRateLimiter(max_requests=30, window_seconds=60, max_keys=10000)
        self.peer_budget = InMemoryRateLimiter(max_requests=240, window_seconds=60, max_keys=10000)
        self.user_budget = InMemoryRateLimiter(max_requests=120, window_seconds=60, max_keys=10000)

    def reserve(self, websocket: WebSocket, peer: str) -> ChatConnection | None:
        # Pending authentication occupies capacity, preventing unauthenticated floods.
        if (not self.connect_budget.consume(peer).allowed
                or len(self.connections) >= self.max_connections
                or sum(c.peer == peer for c in self.connections) >= self.max_connections_per_peer):
            return None
        connection = ChatConnection(websocket, peer, asyncio.Queue(maxsize=self.max_queue))
        self.connections.add(connection)
        return connection

    def authenticate(self, connection: ChatConnection, user_id: str,
                     expires_at: float, authorize: Authorize) -> bool:
        if (connection.closed or expires_at <= self.now()
                or sum(c.user_id == user_id for c in self.connections) >= self.max_connections_per_user):
            return False
        connection.user_id, connection.expires_at, connection.authorize = user_id, expires_at, authorize
        connection.writer = asyncio.create_task(self._write(connection))
        connection.expiry = asyncio.create_task(self._expire(connection))
        return True

    def consume_frame(self, connection: ChatConnection) -> bool:
        return (self.peer_budget.consume(connection.peer).allowed
                and (connection.user_id is None or self.user_budget.consume(connection.user_id).allowed))

    def subscribe(self, connection: ChatConnection, reference: str) -> bool:
        if connection.closed:
            return False
        if reference not in connection.subscriptions and len(connection.subscriptions) >= self.max_subscriptions:
            return False
        connection.subscriptions.add(reference)
        return True

    async def enqueue(self, connection: ChatConnection, payload: dict[str, Any],
                      conversation_ref: str | None = None) -> None:
        if connection.closed:
            return
        try:
            connection.queue.put_nowait((conversation_ref, payload))
        except asyncio.QueueFull:
            await self.close(connection, 1013)

    async def publish(self, conversation_ref: str, payload: dict[str, Any]) -> None:
        # One slow consumer must not serialize timeout delays for other recipients.
        await asyncio.gather(*(self.enqueue(c, payload, conversation_ref)
            for c in tuple(self.connections) if conversation_ref in c.subscriptions))

    async def _write(self, connection: ChatConnection) -> None:
        try:
            while not connection.closed:
                reference, payload = await connection.queue.get()
                if connection.expires_at <= self.now():
                    await self.close(connection, 4401)
                    return
                assert connection.authorize is not None and connection.user_id is not None
                # Check at drain time, not enqueue time: queued bytes can outlive access.
                await connection.authorize(connection.user_id, reference)
                if connection.closed or connection.expires_at <= self.now():
                    await self.close(connection, 4401)
                    return
                async with connection.send_lock:
                    await asyncio.wait_for(connection.websocket.send_json(payload), self.send_timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.close(connection, 1008)

    async def _expire(self, connection: ChatConnection) -> None:
        await asyncio.sleep(max(0, connection.expires_at - self.now()))
        await self.close(connection, 4401)

    async def close(self, connection: ChatConnection, code=1000) -> None:
        if connection.closed:
            return
        connection.closed = True
        self.connections.discard(connection)
        connection.subscriptions.clear()
        while not connection.queue.empty():
            connection.queue.get_nowait()
        current = asyncio.current_task()
        tasks = []
        for task in (connection.writer, connection.expiry):
            if task is not None and task is not current:
                task.cancel()
                tasks.append(task)
        try:
            async with connection.send_lock:
                await asyncio.wait_for(connection.websocket.close(code=code), self.send_timeout)
        except (RuntimeError, OSError, TimeoutError):
            pass
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        await asyncio.gather(*(self.close(c, 1001) for c in tuple(self.connections)))
