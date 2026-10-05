from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import logging
import pytest
from PIL import Image, PngImagePlugin
from app.services.storage_service import LocalPrivateStorage, UnsafeEvidence, sanitize_image
from app.core.evidence_security import EvidenceAccessLogFilter


def png(size=(10, 10)):
    out = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "synthetic metadata")
    Image.new("RGB", size).save(out, "PNG", pnginfo=metadata)
    return out.getvalue()


def test_reencoding_discards_metadata_and_trailing_payload():
    cleaned = sanitize_image(png() + b"<script>synthetic</script>", "proof.png", "image/png")
    with Image.open(BytesIO(cleaned.data)) as image:
        assert not image.info
    assert b"synthetic" not in cleaned.data


@pytest.mark.parametrize("filename", ["../p.png", "p.exe.png", "p.png.exe", "p:stream.png",
                                     ".p.png", "p\\x.png", "p%00.png", "p\u202e.png"])
def test_filename_attacks_rejected(filename):
    with pytest.raises(UnsafeEvidence):
        sanitize_image(png(), filename, "image/png")


def test_dimensions_limited_before_full_decode():
    with pytest.raises(UnsafeEvidence):
        sanitize_image(png((6001, 1)), "wide.png", "image/png")


def test_storage_path_traversal_rejected(tmp_path):
    storage = LocalPrivateStorage(tmp_path)
    for key in ("../outside", "/outside", "x" * 64, "..", "A" * 64):
        with pytest.raises(UnsafeEvidence):
            storage.read(key)


def test_storage_collision_never_deletes_existing_file(tmp_path, monkeypatch):
    storage = LocalPrivateStorage(tmp_path)
    key = storage.upload(b"original")
    monkeypatch.setattr("app.services.storage_service.secrets.token_hex", lambda _: key)
    with pytest.raises(FileExistsError):
        storage.upload(b"replacement")
    assert storage.read(key) == b"original"


def ticket(storage, key):
    return storage.issue_download_ticket(key, actor_id="owner", reference="review",
                                         evidence_type="SELFIE")


def test_signed_access_tamper_binding_expiry_replay(tmp_path):
    now = [0]
    storage = LocalPrivateStorage(tmp_path, clock=lambda: now[0])
    key = storage.upload(b"synthetic")
    value = ticket(storage, key)
    with pytest.raises(UnsafeEvidence):
        storage.redeem(value, "other")
    with pytest.raises(UnsafeEvidence):
        storage.redeem(value[:-1] + ("0" if value[-1] != "0" else "1"), "owner")
    assert storage.redeem(value, "owner")[0] == key
    with pytest.raises(UnsafeEvidence):
        storage.redeem(value, "owner")
    value = ticket(storage, key)
    now[0] = 61
    with pytest.raises(UnsafeEvidence):
        storage.redeem(value, "owner")


def test_access_log_filter_suppresses_capability_url():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s %s %s %s %s",
                              ("peer", "GET", "/api/v1/seller-verification/evidence/content?ticket=synthetic", "1.1", 200), None)
    assert not EvidenceAccessLogFilter().filter(record)


def test_ticket_memory_bound(tmp_path):
    storage = LocalPrivateStorage(tmp_path)
    storage.tickets = {str(i): (storage.clock() + 60, "u", "k", "r", "t") for i in range(1000)}
    with pytest.raises(UnsafeEvidence):
        ticket(storage, "key")


def test_concurrent_ticket_replay_has_exactly_one_winner(tmp_path):
    storage = LocalPrivateStorage(tmp_path)
    value = ticket(storage, storage.upload(b"synthetic"))
    barrier = Barrier(2)
    def redeem():
        barrier.wait(timeout=5)
        try:
            storage.redeem(value, "owner")
            return True
        except UnsafeEvidence:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: redeem(), range(2)))
    assert sorted(results) == [False, True]
