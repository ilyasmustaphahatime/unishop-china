from app.core.rate_limit import InMemoryRateLimiter


class MutableMonotonicClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_rate_limiter_blocks_excess_requests_and_recovers_after_window() -> None:
    clock = MutableMonotonicClock()
    limiter = InMemoryRateLimiter(
        max_requests=2,
        window_seconds=60,
        max_keys=100,
        now_provider=clock,
    )

    assert limiter.consume("client-a").allowed is True
    assert limiter.consume("client-a").allowed is True
    blocked = limiter.consume("client-a")
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 60

    clock.advance(60)

    assert limiter.consume("client-a").allowed is True


def test_rate_limiter_keeps_client_keys_isolated() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)

    assert limiter.consume("client-a").allowed is True
    assert limiter.consume("client-a").allowed is False
    assert limiter.consume("client-b").allowed is True


def test_rate_limiter_bounds_unique_client_memory() -> None:
    limiter = InMemoryRateLimiter(
        max_requests=1,
        window_seconds=60,
        max_keys=2,
    )

    assert limiter.consume("oldest-client").allowed is True
    assert limiter.consume("second-client").allowed is True
    assert limiter.consume("third-client").allowed is True

    assert limiter.consume("oldest-client").allowed is True
