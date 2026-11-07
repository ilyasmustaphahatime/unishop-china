"""Pre-parser chat HTTP budgets, actual-byte bounds and unambiguous JSON."""
import json

from fastapi.responses import JSONResponse

from app.core.http_input import bounded_json_body
from app.core.rate_limit import InMemoryRateLimiter


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field.")
        result[key] = value
    return result


class ChatRequestBoundary:
    def __init__(self, app, prefix):
        self.app = app
        self.path = f"{prefix}/chat"
        self.read = InMemoryRateLimiter(max_requests=240, window_seconds=60, max_keys=10000)
        self.write = InMemoryRateLimiter(max_requests=60, window_seconds=60, max_keys=10000)

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] == "OPTIONS"
                or not (scope["path"] == self.path or scope["path"].startswith(self.path + "/"))):
            return await self.app(scope, receive, send)
        peer = (scope.get("client") or ("unknown",))[0]
        decision = (self.read if scope["method"] == "GET" else self.write).consume(peer)
        body = b""
        error = None
        if not decision.allowed:
            error = (429, "Too many chat requests.")
        elif b"%" in scope.get("raw_path", b""):
            error = (404, "Conversation not found.")
        elif len(scope.get("query_string", b"")) > 1200:
            error = (413, "Chat request exceeds input limits.")
        else:
            try:
                body = await bounded_json_body(receive, maximum_bytes=1024, timeout_seconds=5)
            except ValueError:
                error = (413, "Chat request exceeds input limits.")
            except TimeoutError:
                error = (408, "Chat request timed out.")
            except ConnectionError:
                return
            accepts_body = scope["method"] == "POST" and (
                scope["path"] == self.path + "/conversations"
                or scope["path"].endswith("/wechat/approve")
            )
            if error is None and body:
                if not accepts_body:
                    error = (422, "This operation does not accept a request body.")
                else:
                    types = [value for key, value in scope.get("headers", []) if key == b"content-type"]
                    if len(types) != 1 or types[0].split(b";", 1)[0].strip().lower() != b"application/json":
                        error = (415, "Use an application/json request.")
                    else:
                        try:
                            parsed = json.loads(body, object_pairs_hook=_unique_object)
                            if not isinstance(parsed, dict):
                                raise ValueError
                        except (ValueError, UnicodeError, RecursionError):
                            error = (422, "Invalid chat request.")
        if error:
            headers = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
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
