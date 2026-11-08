"""Pre-parser budgets, bounded bodies, duplicate-key rejection and safe failures."""
import asyncio
import logging
import pytest
from app.common.offers import OfferError
from app.core.offer_limits import clear_offer_limits, consume_offer_limit, offer_limiters
from app.core.offer_security import OfferRequestBoundary
from app.core.rate_limit import InMemoryRateLimiter
from app.core.chat_logging import ChatTransportLogFilter
from tests.unit.test_chat_security import boundary_request


@pytest.mark.parametrize("body,path,method,query,expected", [
    (b'{"amount":"1","amount":"2"}', "/offers", "POST", b"", 422),
    (b'{"amount":NaN}', "/offers", "POST", b"", 422),
    (b'{"amount":Infinity}', "/offers", "POST", b"", 422),
    (b"[1]", "/offers", "POST", b"", 422),
    (b"{", "/offers", "POST", b"", 422),
    (b"\xff", "/offers", "POST", b"", 422),
    (b"x" * 1025, "/offers", "POST", b"", 413),
    (b"{}", "/offers/of-test/accept", "POST", b"", 422),
    (b"{}", "/offers", "GET", b"", 422),
    (b"{}", "/deals/dl-test", "GET", b"", 422),
    (b"", "/offers", "GET", b"x" * 1201, 413),
    (b"", "/offers/of-%61", "GET", b"", 404),
])
def test_rejected_before_application(body, path, method, query, expected):
    async def app(*args):
        pytest.fail("Rejected input reached application.")
    sent = asyncio.run(boundary_request(OfferRequestBoundary(app, "/api/v1"),
        body=body, path="/api/v1"+path, method=method, query=query))
    assert sent[0]["status"] == expected
    assert (b"cache-control", b"no-store") in sent[0]["headers"]


@pytest.mark.parametrize("headers", [[], [(b"content-type", b"text/plain")],
    [(b"content-type", b"application/json"), (b"content-type", b"application/json")]])
def test_content_type_is_unambiguous(headers):
    async def app(*args):
        pytest.fail("Rejected content type reached application.")
    sent = asyncio.run(boundary_request(OfferRequestBoundary(app, "/api/v1"),
        body=b"{}", path="/api/v1/offers", headers=headers))
    assert sent[0]["status"] == 415


def test_bad_json_consumes_peer_budget_without_authentication():
    async def app(*args):
        pytest.fail("Malformed request reached application.")
    boundary = OfferRequestBoundary(app, "/api/v1")
    boundary.write = InMemoryRateLimiter(max_requests=2, window_seconds=60, max_keys=1)
    codes = [asyncio.run(boundary_request(boundary, body=b"{", path="/api/v1/offers"))[0]["status"] for _ in range(3)]
    assert codes == [422, 422, 429]


def test_account_budget_is_bounded_and_fails_closed(monkeypatch):
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60, max_keys=1)
    monkeypatch.setitem(offer_limiters, "write", limiter)
    clear_offer_limits()
    consume_offer_limit("write", "synthetic-user")
    consume_offer_limit("write", "synthetic-user")
    for actor in ("synthetic-user", "another-user"):
        with pytest.raises(OfferError) as caught:
            consume_offer_limit("write", actor)
        assert caught.value.status == 429
    assert len(limiter._requests) == 1


@pytest.mark.parametrize("path", ["/api/v1/offers", "/api/v1/offers/of-123", "/api/v1/deals", "/api/v1/deals/dl-123"])
def test_transport_logs_drop_rejected_url_credentials_and_private_cursors(path):
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s %s", ("GET", path+"?access_token=synthetic-secret"), None)
    assert not ChatTransportLogFilter().filter(record)
