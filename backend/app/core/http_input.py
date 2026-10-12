"""Bound actual request bytes and elapsed input time, not untrusted length headers."""
import asyncio


async def bounded_json_body(receive, *, maximum_bytes: int, timeout_seconds: int = 15):
    body = bytearray()
    async with asyncio.timeout(timeout_seconds):
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise ConnectionError
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > maximum_bytes:
                raise ValueError("Request body limit exceeded.")
            body.extend(chunk)
            if not message.get("more_body", False):
                return bytes(body)
