"""Limit seller ingress before parsing and suppress private-download access logs."""
import asyncio
import logging
from fastapi.responses import JSONResponse
from app.core.rate_limit import InMemoryRateLimiter
from app.services.storage_service import MAX_BYTES


class EvidenceAccessLogFilter(logging.Filter):
    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            return "/seller-verification/evidence/content" not in str(args[2])
        return True


def install_evidence_log_filter():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, EvidenceAccessLogFilter) for f in logger.filters):
        logger.addFilter(EvidenceAccessLogFilter())


class EvidenceUploadBoundary:
    def __init__(self, app, prefix: str):
        self.app = app
        self.seller_path = prefix + "/seller-verification"
        self.admin_path = prefix + "/admin/seller-verifications"
        self.path = prefix + "/seller-verification/evidence"
        self.slots = asyncio.Semaphore(4)
        self.limiter = InMemoryRateLimiter(max_requests=36, window_seconds=60, max_keys=10000)
        self.peer_limits = {
            name: InMemoryRateLimiter(max_requests=count, window_seconds=60, max_keys=10000)
            for name, count in {"submission": 15, "admin": 90, "read": 180}.items()
        }

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def reject(status, message):
            response = JSONResponse({"detail": message}, status_code=status, headers={
                "Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
                **({"Retry-After": "60"} if status == 429 else {}),
            })
            await response(scope, receive, send)

        host = (scope.get("client") or ("unknown",))[0]
        path = scope["path"]
        upload = path == self.path and scope["method"] == "POST"
        if not upload:
            # FastAPI parses JSON before dependencies. Invalid JSON must still
            # consume a bounded, actual-peer budget; never trust forwarded headers.
            namespace = (
                "admin" if path == self.admin_path or path.startswith(self.admin_path + "/")
                else "submission" if path == self.seller_path or path == self.seller_path + "/"
                else "read" if path.startswith(self.seller_path + "/") else None
            )
            if namespace and not self.peer_limits[namespace].consume(host).allowed:
                return await reject(429, "Too many verification requests.")
            return await self.app(scope, receive, send)
        if not self.limiter.consume(host).allowed or self.slots.locked():
            return await reject(429, "Too many uploads.")
        headers = dict(scope.get("headers", []))
        if not headers.get(b"authorization", b"").lower().startswith(b"bearer "):
            return await reject(401, "Authentication required.")
        maximum = MAX_BYTES + 65536
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0 or length > maximum:
                return await reject(413, "Upload is too large.")
        except ValueError:
            return await reject(400, "Invalid request.")
        async with self.slots:
            chunks = []
            size = 0
            try:
                async with asyncio.timeout(30):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        size += len(chunk)
                        if size > maximum:
                            return await reject(413, "Upload is too large.")
                        chunks.append(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(408, "Upload timed out.")
            body = b"".join(chunks)
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()
            await self.app(scope, replay, send)
