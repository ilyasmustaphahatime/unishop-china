"""Bound authentication input before JSON parsing, dependencies or password work."""
import json

from fastapi.responses import JSONResponse

from app.core.http_input import bounded_json_body
from app.core.rate_limit import InMemoryRateLimiter


auth_request_rate_limiter = InMemoryRateLimiter(
    max_requests=240, window_seconds=60, max_keys=10000,
)


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field.")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Invalid JSON constant.")


class AuthRequestBoundary:
    """Additional peer budget; existing account/operation limits remain unchanged."""

    def __init__(self, app, prefix):
        self.app = app
        self.path = prefix + "/auth"

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] == "OPTIONS"
                or not (scope["path"] == self.path or scope["path"].startswith(self.path + "/"))):
            return await self.app(scope, receive, send)
        peer = (scope.get("client") or ("unknown",))[0]
        decision = auth_request_rate_limiter.consume(peer)
        code, detail, body = 0, "", b""
        if not decision.allowed:
            code, detail = 429, "Too many authentication requests."
        else:
            try:
                body = await bounded_json_body(receive, maximum_bytes=16384, timeout_seconds=5)
            except ValueError:
                code, detail = 413, "Request exceeds input limits."
            except TimeoutError:
                code, detail = 408, "Request input deadline exceeded."
            except ConnectionError:
                return
            if body and not code:
                types = [v for k, v in scope.get("headers", []) if k == b"content-type"]
                content_type = types[0].split(b";", 1)[0].strip().lower() if len(types) == 1 else b""
                if not (content_type == b"application/json"
                        or content_type.startswith(b"application/") and content_type.endswith(b"+json")):
                    code, detail = 415, "Use application/json."
                else:
                    try:
                        json.loads(body, object_pairs_hook=_unique_fields, parse_constant=_invalid_constant)
                    except (ValueError, UnicodeError, RecursionError):
                        code = 422
                        detail = [{"type": "json_invalid", "loc": ["body"], "msg": "Invalid JSON."}]
        if code:
            headers = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
            if code == 429:
                headers["Retry-After"] = str(decision.retry_after_seconds or 1)
            return await JSONResponse({"detail": detail}, status_code=code, headers=headers)(scope, receive, send)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
