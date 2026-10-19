"""Actual-byte and peer budgets apply even before JSON/auth validation."""
from fastapi.responses import JSONResponse

from app.core.http_input import bounded_json_body
from app.core.rate_limit import InMemoryRateLimiter


class PersonalizationRequestBoundary:
    def __init__(self, app, prefix):
        self.app = app
        self.paths = tuple(f"{prefix}/me/{name}" for name in ("favorites", "recently-viewed"))
        self.lookup = self.paths[0] + "/lookup"
        self.read = InMemoryRateLimiter(max_requests=240, window_seconds=60, max_keys=10000)
        self.write = InMemoryRateLimiter(max_requests=120, window_seconds=60, max_keys=10000)

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] == "OPTIONS" or not any(
                scope["path"] == p or scope["path"].startswith(p + "/") for p in self.paths)):
            return await self.app(scope, receive, send)
        peer = (scope.get("client") or ("unknown",))[0]
        decision = (self.read if scope["method"] == "GET" else self.write).consume(peer)
        error = None
        body = b""
        lookup = scope["method"] == "POST" and scope["path"] == self.lookup
        if not decision.allowed:
            error = (429, "Too many personal listing requests.")
        elif b"%" in scope.get("raw_path", b""):
            error = (404, "Listing not found.")
        elif len(scope.get("query_string", b"")) > 1024:
            error = (413, "Personal listing request exceeds input limits.")
        else:
            try:
                body = await bounded_json_body(receive, maximum_bytes=4096)
            except (ValueError, TimeoutError) as exc:
                error = (413 if isinstance(exc, ValueError) else 408,
                         "Personal listing request exceeds input limits.")
            except ConnectionError:
                return
            if error is None:
                if lookup:
                    headers = dict(scope.get("headers", []))
                    content_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
                    if content_type != b"application/json":
                        error = (415, "Use an application/json request.")
                elif body:
                    error = (422, "This operation does not accept a request body.")
        if error:
            headers = {"Cache-Control": "no-store", "Pragma": "no-cache",
                       "Referrer-Policy": "no-referrer"}
            if error[0] == 429:
                headers["Retry-After"] = str(decision.retry_after_seconds or 1)
            return await JSONResponse({"detail": error[1]}, status_code=error[0],
                                      headers=headers)(scope, receive, send)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
