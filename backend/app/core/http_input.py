"""Bound actual request bytes and elapsed input time, not untrusted length headers."""
import asyncio
from contextlib import asynccontextmanager
from tempfile import SpooledTemporaryFile


class RequestBodyLimitExceeded(ValueError):
    """Neutral actual-byte bound, distinguishable from parser/decoder errors."""


@asynccontextmanager
async def bounded_spooled_body(receive, *, maximum_bytes: int, timeout_seconds: int = 15):
    """Limit bytes BEFORE the framework parser; spool beyond 1 MiB, always close."""
    with SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as body:
        size = 0
        async with asyncio.timeout(timeout_seconds):
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    raise ConnectionError
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > maximum_bytes:
                    raise RequestBodyLimitExceeded("Request body limit exceeded.")
                await asyncio.to_thread(body.write, chunk)
                if not message.get("more_body", False):
                    break
        await asyncio.to_thread(body.seek, 0)
        yield body


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
