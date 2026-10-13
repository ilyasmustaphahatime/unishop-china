"""Cheap peer budgets and actual-byte bounds before multipart parsing."""
import asyncio
from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders

from app.common.product_image_rules import MAX_MULTIPART_BYTES
from app.core.http_input import bounded_json_body, bounded_spooled_body
from app.core.rate_limit import InMemoryRateLimiter


def image_request_path(path, prefix):
    for base in (prefix + "/products/", prefix + "/seller/products/"):
        if path.startswith(base):
            parts = path[len(base):].split("/")
            if len(parts) >= 2 and parts[1] == "images":
                return True
    return False


class ImageIntakeBusy(RuntimeError):
    pass


class ProductImageRequestBoundary:
    def __init__(self, app, prefix):
        self.app, self.prefix = app, prefix
        self.upload = InMemoryRateLimiter(max_requests=36, window_seconds=600, max_keys=10000)
        self.write = InMemoryRateLimiter(max_requests=90, window_seconds=60, max_keys=10000)
        self.read = InMemoryRateLimiter(max_requests=180, window_seconds=60, max_keys=10000)
        self.slots = asyncio.Semaphore(2)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or not image_request_path(scope["path"], self.prefix):
            return await self.app(scope, receive, send)
        original_send = send

        async def protected_send(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers.update({"Cache-Control": "no-store", "Pragma": "no-cache",
                    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})
            await original_send(message)

        send = protected_send
        headers = dict(scope.get("headers", []))
        method = scope["method"]
        upload = method == "POST"
        mutation = method in {"POST", "PATCH", "DELETE"}
        peer = (scope.get("client") or ("unknown",))[0]
        decision = (self.upload if upload else self.write if mutation else self.read).consume(peer)

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status, headers={
                "Cache-Control": "no-store", "Pragma": "no-cache",
                "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
                **({"Retry-After": str(decision.retry_after_seconds or 30)} if status == 429 else {}),
            })(scope, receive, send)

        if not decision.allowed:
            return await reject(429, "Too many image requests.")
        if b"%" in scope.get("raw_path", b""):
            return await reject(404, "Image not found.")
        if upload:
            if not headers.get(b"authorization", b"").lower().startswith(b"bearer "):
                return await reject(401, "Authentication required.")
            if headers.get(b"content-type", b"").split(b";", 1)[0].lower().strip() != b"multipart/form-data":
                return await reject(415, "Use a multipart/form-data request.")
            try:
                length = int(headers.get(b"content-length", b"0"))
                if length < 0 or length > MAX_MULTIPART_BYTES:
                    return await reject(413, "Image request exceeds input limits.")
            except ValueError:
                return await reject(400, "Invalid image request.")
            @asynccontextmanager
            async def admitted_intake(receive_body):
                # Invoked by the file dependency only AFTER cryptographic auth,
                # user budgets and service-owned owner/quota preflight. Never
                # let an invalid bearer reserve a slow-body slot or spool bytes.
                if self.slots.locked():
                    raise ImageIntakeBusy
                async with self.slots, bounded_spooled_body(receive_body, maximum_bytes=MAX_MULTIPART_BYTES) as body:
                    yield body

            scope["product_image_intake"] = admitted_intake
            return await self.app(scope, receive, send)
        if method == "PATCH":
            if headers.get(b"content-type", b"").split(b";", 1)[0].lower().strip() != b"application/json":
                return await reject(415, "Use an application/json request.")
        if method in {"PATCH", "DELETE"}:
            try:
                body = await bounded_json_body(receive, maximum_bytes=32 * 1024)
            except ValueError:
                return await reject(413, "Image request exceeds input limits.")
            except TimeoutError:
                return await reject(408, "Image request timed out.")
            except ConnectionError:
                return
            if method == "DELETE" and body.strip() not in {b"", b"{}"}:
                return await reject(422, "Image delete does not accept fields.")
            delivered = False

            async def replay_json():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}

            return await self.app(scope, replay_json, send)
        return await self.app(scope, receive, send)
