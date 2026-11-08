"""Bounded per-process budgets; no distributed quota is claimed."""
from app.common.offers import OfferError
from app.core.rate_limit import InMemoryRateLimiter

offer_limiters = {name: InMemoryRateLimiter(max_requests=count, window_seconds=60, max_keys=10000)
                  for name, count in (("read", 120), ("write", 20))}


def consume_offer_limit(action, actor):
    if not offer_limiters[action].consume(actor).allowed:
        raise OfferError("Too many offer requests.", 429)


def clear_offer_limits():
    for limiter in offer_limiters.values():
        limiter.clear()
