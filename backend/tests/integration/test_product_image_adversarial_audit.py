"""Independent protocol, transaction-interruption and authority regressions."""
import asyncio
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser
from starlette.datastructures import FormData

from app.models import ProductImage, SellerVerification
from app.models.seller_verification import VerificationStatus
from app.common.product_image_rules import MAX_RAW_BYTES
from tests.integration.test_product_listings import world as world, headers
from tests.integration.test_product_images import image_world as image_world, images, count, upload
from tests.product_image_fixtures import raster


def test_interrupted_completed_file_never_reaches_parser_or_storage(image_world, monkeypatch):
    from app.core import http_input

    w = image_world
    spools = []
    original = http_input.SpooledTemporaryFile

    def tracked_spool(*args, **kwargs):
        spool = original(*args, **kwargs)
        spools.append(spool)
        return spool

    monkeypatch.setattr(http_input, "SpooledTemporaryFile", tracked_spool)

    async def unexpected_parse(*args, **kwargs):
        pytest.fail("Interrupted transport reached multipart parsing.")

    monkeypatch.setattr(MultiPartParser, "parse", unexpected_parse)
    payload = (b'--audit\r\nContent-Disposition: form-data; name="file"; filename="synthetic.png"\r\n'
               b'Content-Type: image/png\r\n\r\n' + raster() + b"\r\n--audit\r\n")

    async def run():
        delivered, status, messages = False, None, []
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": "POST", "scheme": "http", "path": w.own,
            "raw_path": w.own.encode(), "root_path": "", "query_string": b"",
            "headers": [(b"authorization", headers(w.owner)["Authorization"].encode()),
                        (b"content-type", b"multipart/form-data; boundary=audit")],
            "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8000)}

        async def receive():
            nonlocal delivered
            assert not w.db.in_transaction(), "Input wait retained SQL locks."
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": True}

        async def send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                messages.append(message.get("body", b""))

        await asyncio.wait_for(w.client.app(scope, receive, send), timeout=5)
        assert status == 400
        assert b"".join(messages) == b'{"detail":"Image upload interrupted."}'

    asyncio.run(run())
    assert len(spools) == 1 and all(spool.closed for spool in spools)
    assert count(w) == 0 and list(w.storage.keys()) == []


@pytest.mark.parametrize("operation", ["reorder", "delete"])
def test_failure_after_temporary_positions_flush_restores_committed_set(image_world, monkeypatch, operation):
    w = image_world
    refs = [upload(w).json()["ref"] for _ in range(3)]
    before, keys = images(w), set(w.storage.keys())
    original, interrupted = w.db.flush, []

    def interrupted_flush(*args, **kwargs):
        temporary = any(isinstance(row, ProductImage) and row.position >= 8 for row in w.db.dirty)
        result = original(*args, **kwargs)
        if temporary:
            interrupted.append(True)
            raise RuntimeError("Synthetic intermediate-position interruption")
        return result

    with monkeypatch.context() as fault:
        fault.setattr(w.db, "flush", interrupted_flush)
        response = (w.client.patch(w.own + "/order", headers=headers(w.owner), json={"images": refs[::-1]})
                    if operation == "reorder" else w.client.delete(w.own + "/" + refs[0], headers=headers(w.owner)))
        assert response.status_code == 503
    assert interrupted == [True] and w.db.is_active
    assert images(w) == before and set(w.storage.keys()) == keys
    assert count(w) == 3


@pytest.mark.parametrize("state", [VerificationStatus.PENDING, VerificationStatus.UNDER_REVIEW])
def test_pending_review_is_not_upload_authority_but_allows_owner_cleanup(image_world, state):
    w = image_world
    ref = upload(w).json()["ref"]
    attempt = w.db.scalar(select(SellerVerification).where(SellerVerification.user_id == w.owner.id))
    attempt.status, attempt.reviewed_at, attempt.reviewed_by = state, None, None
    if state == VerificationStatus.PENDING:
        attempt.submitted_at = None
    w.db.commit()
    assert upload(w).status_code == 403
    assert w.client.patch(w.own + "/order", headers=headers(w.owner), json={"images": [ref]}).status_code == 403
    assert w.client.get(w.own + "/" + ref, headers=headers(w.owner)).status_code == 200
    assert w.client.delete(w.own + "/" + ref, headers=headers(w.owner)).status_code == 204


@pytest.mark.parametrize("ending", ["unclosed_file", "unfinished_next_part", "truncated_header", "truncated_pixels"])
def test_truncated_multipart_cannot_commit_an_image(image_world, ending):
    w = image_world
    header = b'--audit-boundary\r\nContent-Disposition: form-data; name="file"; filename="private.png"\r\nContent-Type: image/png\r\n\r\n'
    data = raster()
    payload = {
        "unclosed_file": header + data,
        "unfinished_next_part": header + data + b"\r\n--audit-boundary\r\n",
        "truncated_header": header[:40],
        "truncated_pixels": header + data[:12] + b"\r\n--audit-boundary--\r\n",
    }[ending]
    response = w.client.post(w.own, headers={**headers(w.owner), "Content-Type": "multipart/form-data; boundary=audit-boundary"}, content=payload)
    assert response.status_code in {400, 422}
    assert count(w) == 0 and list(w.storage.keys()) == []


@pytest.mark.parametrize("extra", [0, 1])
def test_exact_raw_byte_boundary_is_independent_of_small_decoded_pixels(image_world, extra):
    w = image_world
    base = raster("JPEG")
    remaining = MAX_RAW_BYTES + extra - len(base)
    parts = [base[:2]]
    while remaining:
        size = min(65533, remaining - 4)
        if remaining - size - 4 in {1, 2, 3}:
            size -= 4
        assert size >= 0
        parts.append(b"\xff\xfe" + (size + 2).to_bytes(2, "big") + b"x" * size)
        remaining -= size + 4
    parts.append(base[2:])
    payload = b"".join(parts)
    assert len(payload) == MAX_RAW_BYTES + extra
    response = upload(w, data=payload, type="application/octet-stream")
    assert response.status_code == (422 if extra else 201)
    if extra:
        assert count(w) == 0 and list(w.storage.keys()) == []
    else:
        assert response.json()["file_size"] < 100_000 and count(w) == 1
        assert response.json()["width"] == 12 and response.json()["height"] == 8


def test_multipart_filesystem_failure_is_safe_unavailable_not_a_traceback(image_world, monkeypatch):
    w = image_world

    async def failed_parse(*args, **kwargs):
        raise OSError("SYNTHETIC PRIVATE MULTIPART PATH")

    monkeypatch.setattr(MultiPartParser, "parse", failed_parse)
    with TestClient(w.client.app, raise_server_exceptions=False) as client:
        response = client.post(w.own, headers=headers(w.owner),
                               files={"file": ("private.png", raster(), "image/png")})
    assert response.status_code == 503
    assert response.json() == {"detail": "Image upload temporarily unavailable."}
    assert "SYNTHETIC PRIVATE" not in response.text
    assert count(w) == 0 and list(w.storage.keys()) == []


def test_multipart_cleanup_failure_is_handled_before_response_starts(image_world, monkeypatch):
    w = image_world
    close = FormData.close

    async def failed_close(form):
        await close(form)
        raise OSError("SYNTHETIC PRIVATE CLEANUP PATH")

    monkeypatch.setattr(FormData, "close", failed_close)
    response = upload(w)
    assert response.status_code == 503
    assert response.json() == {"detail": "Image upload temporarily unavailable."}
    assert "SYNTHETIC PRIVATE" not in response.text
    # Service commit precedes request-spool cleanup; do not undo valid metadata
    # or replay the upload. Clients must inspect own images after ambiguity.
    assert count(w) == 1 and len(list(w.storage.keys())) == 1


def test_invalid_bearer_slow_bodies_cannot_reserve_all_global_upload_slots(image_world):
    w = image_world
    head = b'--audit\r\nContent-Disposition: form-data; name="file"; filename="synthetic.png"\r\nContent-Type: image/png\r\n\r\n'
    payload = head + raster() + b"\r\n--audit--\r\n"

    async def run():
        release, invalid_reads = asyncio.Event(), []

        async def invoke(authorization, *, slow=False):
            started, delivered, status = False, False, None
            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1", "method": "POST", "scheme": "http", "path": w.own,
                "raw_path": w.own.encode(), "root_path": "", "query_string": b"",
                "headers": [(b"authorization", authorization.encode()),
                            (b"content-type", b"multipart/form-data; boundary=audit"),
                            (b"content-length", str(len(payload)).encode())],
                "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8000)}

            async def receive():
                nonlocal delivered
                if not slow and not started:
                    assert not w.db.in_transaction(), "SQL locks were held while awaiting upload input."
                if slow and not started:
                    invalid_reads.append(True)
                    await release.wait()
                if delivered:
                    return {"type": "http.disconnect"}
                delivered = True
                return {"type": "http.request", "body": payload, "more_body": False}

            async def send(message):
                nonlocal started, status
                if message["type"] == "http.response.start":
                    started, status = True, message["status"]

            await asyncio.wait_for(w.client.app(scope, receive, send), timeout=5)
            return status

        attackers = [asyncio.create_task(invoke("Bearer deliberately-invalid", slow=True)) for _ in range(2)]
        try:
            await asyncio.sleep(0.03)  # Controlled scheduling, not a load/stress test.
            valid_status = await invoke(headers(w.owner)["Authorization"])
        finally:
            release.set()
            denied = await asyncio.gather(*attackers)
        assert valid_status == 201, "Unauthenticated slow bodies reserved the entire upload capacity."
        assert denied == [401, 401] and invalid_reads == []

    asyncio.run(run())
    assert count(w) == 1


@pytest.mark.parametrize("denial,expected", [("ineligible", 403), ("foreign", 404), ("full", 409)])
def test_owner_eligibility_and_quota_deny_before_any_body_intake(image_world, denial, expected):
    w = image_world
    if denial == "ineligible":
        w.owner.phone_verified = False
        w.db.commit()
    elif denial == "full":
        for _ in range(8):
            assert upload(w).status_code == 201
    authorization = headers(w.other if denial == "foreign" else w.owner)["Authorization"]

    async def run():
        status, started, received = None, False, []
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": "POST", "scheme": "http", "path": w.own,
            "raw_path": w.own.encode(), "root_path": "", "query_string": b"",
            "headers": [(b"authorization", authorization.encode()),
                        (b"content-type", b"multipart/form-data; boundary=audit")],
            "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8000)}

        async def receive():
            if not started:
                received.append(True)
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            nonlocal status, started
            if message["type"] == "http.response.start":
                status, started = message["status"], True

        await asyncio.wait_for(w.client.app(scope, receive, send), timeout=5)
        assert status == expected and received == []

    asyncio.run(run())
    assert count(w) == (8 if denial == "full" else 0)


@pytest.mark.parametrize("error", ["hidden", "invalid_ref", "ineligible"])
def test_image_error_responses_retain_media_security_headers(image_world, error):
    w = image_world
    if error == "ineligible":
        w.owner.phone_verified = False
        w.db.commit()
        response = upload(w)
        assert response.status_code == 403
    else:
        ref = "not-an-image" if error == "invalid_ref" else "img-" + "a" * 32
        response = w.client.get(w.public + "/" + ref)
        assert response.status_code == (422 if error == "invalid_ref" else 404)
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("referrer-policy") == "no-referrer"
