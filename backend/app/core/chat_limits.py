"""Shared HTTP/WebSocket account budgets using the existing bounded limiter.

These limits are per application process, not a distributed quota.
"""
from app.common.chat import ChatError
from app.core.rate_limit import InMemoryRateLimiter

chat_limiters = {
    action: InMemoryRateLimiter(max_requests=maximum, window_seconds=60, max_keys=10000)
    for action, maximum in {"create": 20, "send": 60, "read": 120, "handoff": 20}.items()
}


def consume_chat_limit(action: str, actor_id: str) -> None:
    decision = chat_limiters[action].consume(actor_id)
    if not decision.allowed:
        raise ChatError("Too many chat requests. Try again later.", 429, "chat_rate_limited")


def clear_chat_limits() -> None:
    """Deterministic test/reset hook; not exposed over HTTP."""
    for limiter in chat_limiters.values():
        limiter.clear()
