"""Catalog peer budgets run before FastAPI attempts to parse attacker-controlled JSON."""
import asyncio
from fastapi.responses import JSONResponse

from app.core.rate_limit import InMemoryRateLimiter


class CatalogRequestBoundary:
    def __init__(self, app, prefix: str):
        self.app = app
        self.public_paths = (prefix + "/cities", prefix + "/categories")
        self.admin_paths = (prefix + "/admin/cities", prefix + "/admin/categories")
        self.public = InMemoryRateLimiter(max_requests=180, window_seconds=60, max_keys=10000)
        self.admin = InMemoryRateLimiter(max_requests=90, window_seconds=60, max_keys=10000)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        path = scope["path"]
        admin = any(path == p or path.startswith(p + "/") for p in self.admin_paths)
        public = any(path == p or path.startswith(p + "/") for p in self.public_paths)
        if not (admin or public):
            return await self.app(scope, receive, send)
        limiter = self.admin if admin else self.public
        peer = (scope.get("client") or ("unknown",))[0]
        decision = limiter.consume(peer)
        if not decision.allowed:
            response = JSONResponse({"detail": "Too many catalog requests."}, status_code=429,
                headers={"Retry-After": str(decision.retry_after_seconds or 60), "Cache-Control": "no-store",
                         "Pragma": "no-cache", "Referrer-Policy": "no-referrer"})
            return await response(scope, receive, send)
        if b"%" in scope.get("raw_path", b""):
            response = JSONResponse({"detail": "Catalog resource not found."}, status_code=404,
                                     headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
            return await response(scope, receive, send)
        if admin and scope["method"] in {"POST", "PATCH"}:
            try:
                body = await bounded_catalog_body(receive)
            except (ValueError, TimeoutError) as exc:
                status = 413 if isinstance(exc, ValueError) else 408
                response = JSONResponse({"detail": "Catalog request exceeds input limits."}, status_code=status,
                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
                return await response(scope, receive, send)
            except ConnectionError:
                return
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            return await self.app(scope, replay, send)
        return await self.app(scope, receive, send)


async def bounded_catalog_body(receive):
    """Bound actual bytes, including chunked/lying Content-Length requests."""
    body = bytearray()
    async with asyncio.timeout(15):
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise ConnectionError
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > 16 * 1024:
                raise ValueError("Catalog body limit exceeded.")
            body.extend(chunk)
            if not message.get("more_body", False):
                return bytes(body)
