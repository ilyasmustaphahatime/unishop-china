from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None = None


class InMemoryRateLimiter:
    """Thread-safe sliding-window limiter for one application process."""

    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: int,
        max_keys: int,
        now_provider: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests < 1 or window_seconds < 1 or max_keys < 1:
            raise ValueError("Rate-limit values must be positive.")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self.now_provider = now_provider
        self._requests: dict[str, deque[float]] = {}
        self._lock = RLock()

    def consume(self, key: str) -> RateLimitDecision:
        now = self.now_provider()
        cutoff = now - self.window_seconds
        with self._lock:
            requests = self._requests.get(key)
            if requests is None:
                self._make_room_for_key(cutoff)
                requests = deque()
                self._requests[key] = requests
            while requests and requests[0] <= cutoff:
                requests.popleft()

            if len(requests) >= self.max_requests:
                retry_after = max(1, math.ceil(self.window_seconds - (now - requests[0])))
                return RateLimitDecision(False, retry_after)

            requests.append(now)
            return RateLimitDecision(True)

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()

    def _make_room_for_key(self, cutoff: float) -> None:
        expired_keys = [
            key for key, requests in self._requests.items() if not requests or requests[-1] <= cutoff
        ]
        for key in expired_keys:
            self._requests.pop(key, None)

        if len(self._requests) >= self.max_keys:
            oldest_key = min(
                self._requests,
                key=lambda key: self._requests[key][-1],
            )
            self._requests.pop(oldest_key, None)
