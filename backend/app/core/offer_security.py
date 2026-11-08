"""Offer/deal peer budgets and actual-byte bounds before parsing or authentication."""
import json

from fastapi.responses import JSONResponse
from app.core.http_input import bounded_json_body
from app.core.rate_limit import InMemoryRateLimiter
from app.common.offers import unique_pairs


class OfferRequestBoundary:
    def __init__(self, app, prefix):
        self.app = app
        self.paths = (prefix + "/offers", prefix + "/deals")
        self.read = InMemoryRateLimiter(max_requests=240, window_seconds=60, max_keys=10000)
        self.write = InMemoryRateLimiter(max_requests=60, window_seconds=60, max_keys=10000)

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] == "OPTIONS"
                or not any(scope["path"] == p or scope["path"].startswith(p + "/") for p in self.paths)):
            return await self.app(scope, receive, send)
        peer = (scope.get("client") or ("unknown",))[0]
        decision = (self.read if scope["method"] == "GET" else self.write).consume(peer)
        error, body = None, b""
        if not decision.allowed:
            error = (429, "Too many offer requests.")
        elif b"%" in scope.get("raw_path", b""):
            error = (404, "Resource not found.")
        elif len(scope.get("query_string", b"")) > 1200:
            error = (413, "Request exceeds input limits.")
        else:
            try:
                body = await bounded_json_body(receive, maximum_bytes=1024, timeout_seconds=5)
            except ValueError:
                error = (413, "Request exceeds input limits.")
            except TimeoutError:
                error = (408, "Request input deadline exceeded.")
            except ConnectionError:
                return
            accepts = scope["method"] == "POST" and (scope["path"] == self.paths[0] or scope["path"].endswith("/counteroffers"))
            if error is None and body:
                if not accepts:
                    error = (422, "This operation does not accept a request body.")
                else:
                    types = [v for k, v in scope.get("headers", []) if k == b"content-type"]
                    if len(types) != 1 or types[0].split(b";", 1)[0].strip().lower() != b"application/json":
                        error = (415, "Use application/json.")
                    else:
                        try:
                            def invalid_constant(value):
                                raise ValueError
                            parsed = json.loads(body, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
                            if not isinstance(parsed, dict):
                                raise ValueError
                        except (ValueError, UnicodeError, RecursionError):
                            error = (422, "Invalid offer request.")
        if error:
            headers = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
            if error[0] == 429:
                headers["Retry-After"] = str(decision.retry_after_seconds or 1)
            return await JSONResponse({"detail": error[1]}, status_code=error[0], headers=headers)(scope, receive, send)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
