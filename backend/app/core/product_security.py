"""Listing budgets and JSON bounds before parsing, including malformed input."""
from fastapi.responses import JSONResponse
from app.core.http_input import bounded_json_body
from app.core.rate_limit import InMemoryRateLimiter
from app.core.product_image_security import image_request_path


class ProductRequestBoundary:
    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix
        self.paths = (prefix + "/products", prefix + "/seller/products")
        self.read = InMemoryRateLimiter(max_requests=180, window_seconds=60, max_keys=10000)
        self.write = InMemoryRateLimiter(max_requests=90, window_seconds=60, max_keys=10000)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or not any(
            scope["path"] == p or scope["path"].startswith(p + "/") for p in self.paths
        ):
            return await self.app(scope, receive, send)
        if image_request_path(scope["path"], self.prefix):
            return await self.app(scope, receive, send)  # Separate bounded multipart/media boundary.
        write = scope["method"] in {"POST", "PATCH"}
        peer = (scope.get("client") or ("unknown",))[0]
        decision = (self.write if write else self.read).consume(peer)
        error = None
        if not decision.allowed:
            error = (429, "Too many listing requests.")
        elif b"%" in scope.get("raw_path", b""):
            error = (404, "Listing not found.")
        elif write:
            headers = dict(scope.get("headers", []))
            if headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower() != b"application/json":
                error = (415, "Use an application/json request.")
            else:
                try:
                    body = await bounded_json_body(receive, maximum_bytes=32 * 1024)
                except (ValueError, TimeoutError) as exc:
                    error = (413 if isinstance(exc, ValueError) else 408, "Listing request exceeds input limits.")
                except ConnectionError:
                    return
        if error:
            headers = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
            if error[0] == 429:
                headers["Retry-After"] = str(decision.retry_after_seconds or 60)
            return await JSONResponse({"detail": error[1]}, status_code=error[0], headers=headers)(scope, receive, send)
        if write:
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            return await self.app(scope, replay, send)
        return await self.app(scope, receive, send)
