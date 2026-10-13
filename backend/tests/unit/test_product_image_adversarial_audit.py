"""Independent bounded attacks; no real media or host-path modification."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Barrier, BoundedSemaphore, Event, Lock
import asyncio
import os
import re
import subprocess

from PIL import Image, PngImagePlugin
import pytest
from starlette import formparsers
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException

from app.api.v1.products.image_dependencies import CompleteImageMultipartParser
from app.common.product_image_rules import MAX_MULTIPART_BYTES, generate_storage_key
from app.services import product_image_sanitizer as sanitizer
from app.services.product_image_storage import LocalProductImageStorage
from tests.product_image_fixtures import raster


def test_nginx_product_upload_contract_matches_actual_intake_budget():
    config = (Path(__file__).resolve().parents[3] / "infrastructure/nginx/nginx.conf").read_text()
    location = re.search(r'location\s+~\s+"\^/api/v1/seller/products/item-\[0-9a-f\]\{24\}/images\$"\s*\{([^}]+)\}', config)
    assert location is not None, "No scoped product-image upload location exists."
    assert f"client_max_body_size {MAX_MULTIPART_BYTES};" in location.group(1)
    assert "proxy_pass http://backend:8000;" in location.group(1)
    assert "client_max_body_size 6m;" in config  # Other endpoints retain their existing cap.


@pytest.mark.parametrize("attack", ["seller-evidence/", "../seller-evidence/", "product-media/../../seller-evidence/"])
def test_product_storage_never_resolves_neighboring_evidence(tmp_path, attack):
    nonce = "a" * 64
    private = tmp_path / "seller-evidence" / nonce
    private.parent.mkdir()
    private.write_bytes(b"SYNTHETIC PRIVATE EVIDENCE")
    storage = LocalProductImageStorage(tmp_path / "products")
    key = "product-media/" + nonce
    storage.save(key, b"SYNTHETIC PRODUCT ONLY")
    try:
        for operation in (storage.read, storage.delete):
            with pytest.raises(OSError):
                operation(attack + nonce)
        assert storage.read(key) == b"SYNTHETIC PRODUCT ONLY"
        assert list(storage.keys()) == [key]
        assert private.read_bytes() == b"SYNTHETIC PRIVATE EVIDENCE"
    finally:
        storage.delete(key)
        private.unlink()


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_icc_comments_and_text_do_not_survive_fresh_pixel_encoding(format):
    source = BytesIO()
    options = {"icc_profile": b"SYNTHETIC PRIVATE ICC", "comment": b"SYNTHETIC PRIVATE COMMENT"}
    if format == "PNG":
        text = PngImagePlugin.PngInfo()
        text.add_text("Comment", "SYNTHETIC PRIVATE COMMENT")
        text.add_text("Author", "SYNTHETIC PRIVATE AUTHOR", zip=True)
        options["pnginfo"] = text
    with Image.new("RGB", (8, 6), (20, 40, 60)) as image:
        image.save(source, format=format, **options)
    original = source.getvalue()
    with Image.open(BytesIO(original)) as image:
        assert image.info.get("icc_profile") == options["icc_profile"]
    result = sanitizer.sanitize_product_image(original)
    with Image.open(BytesIO(result.data)) as clean:
        clean.load()
        assert clean.format == format and (clean.width, clean.height) == (8, 6)
        assert not clean.getexif()
        assert not any(field in clean.info for field in ("icc_profile", "comment", "Comment", "Author"))
    assert b"SYNTHETIC PRIVATE" not in result.data


def test_concurrent_decode_capacity_covers_encoding_and_recovers(monkeypatch):
    payload = raster()
    slots = BoundedSemaphore(2)
    monkeypatch.setattr(sanitizer, "decode_slots", slots)
    entered, release, lock = Event(), Event(), Lock()
    count = 0
    original = Image.Image.save

    def controlled_save(image, *args, **kwargs):
        nonlocal count
        with lock:
            count += 1
            if count == 2:
                entered.set()
        assert release.wait(timeout=5)
        return original(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", controlled_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(sanitizer.sanitize_product_image, payload) for _ in range(2)]
        try:
            assert entered.wait(timeout=5)
            with pytest.raises(sanitizer.ImageProcessingBusy):
                sanitizer.sanitize_product_image(payload)
            assert count == 2
        finally:
            release.set()
        assert all(future.result(timeout=5).mime_type == "image/png" for future in pending)
    assert sanitizer.sanitize_product_image(payload).mime_type == "image/png"
    assert count == 3


@pytest.mark.parametrize("ending", ["complete", "unclosed_file", "unfinished_part", "cancel", "io_error", "parse_error"])
def test_multipart_parser_owns_and_closes_spools_on_all_exit_paths(monkeypatch, ending):
    files = []
    original = formparsers.SpooledTemporaryFile

    def track(*args, **kwargs):
        file = original(*args, **kwargs)
        files.append(file)
        return file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", track)
    header = b'--audit\r\nContent-Disposition: form-data; name="file"; filename="synthetic.png"\r\n\r\n'
    payload = b"x" * (1024 * 1024 + 1)

    async def stream():
        yield header + payload
        if ending == "cancel":
            raise asyncio.CancelledError
        if ending == "io_error":
            raise OSError("Synthetic spool failure")
        if ending == "parse_error":
            raise ValueError("Synthetic parser failure")
        if ending == "complete":
            yield b"\r\n--audit--\r\n"
        elif ending == "unfinished_part":
            yield b"\r\n--audit\r\n"

    async def run():
        parser = CompleteImageMultipartParser(Headers({"Content-Type": "multipart/form-data; boundary=audit"}),
            stream(), max_files=1, max_fields=0)
        if ending == "complete":
            form = await parser.parse()
            assert parser.complete and len(form.multi_items()) == 1
            assert len(files) == 1 and files[0]._rolled and not files[0].closed
            assert await form["file"].read() == payload
            await form.close()
        else:
            error = (asyncio.CancelledError if ending == "cancel" else OSError if ending == "io_error"
                     else ValueError if ending == "parse_error" else MultiPartException)
            with pytest.raises(error):
                await parser.parse()
        assert len(files) == 1 and files[0].closed

    asyncio.run(run())


def test_native_linked_storage_root_cannot_read_or_delete_private_sentinel(tmp_path):
    private_root = tmp_path / "synthetic-evidence"
    key = "product-media/" + "a" * 64
    private_file = private_root / key
    private_file.parent.mkdir(parents=True)
    private_file.write_bytes(b"SYNTHETIC PRIVATE SENTINEL")
    link = tmp_path / "linked-storage"
    assert link.parent.resolve() == tmp_path.resolve()
    if os.name == "nt":
        def quote(path):
            return "'" + str(path).replace("'", "''") + "'"
        command = ("$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path "
                   + quote(link) + " -Target " + quote(private_root) + " | Out-Null")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert link.is_junction()
    else:
        link.symlink_to(private_root, target_is_directory=True)
    try:
        storage = LocalProductImageStorage(link)
        for operation in (lambda: storage.read(key), lambda: storage.delete(key),
                          lambda: storage.save(key, b"UNTRUSTED REPLACEMENT"), lambda: list(storage.keys())):
            with pytest.raises(OSError):
                operation()
        assert private_file.read_bytes() == b"SYNTHETIC PRIVATE SENTINEL"
    finally:
        if os.name == "nt":
            link.rmdir()  # Remove only the owned junction, never recursively follow its target.
        else:
            link.unlink()
        private_file.unlink()


def test_concurrent_atomic_publication_collision_preserves_exact_winner(tmp_path):
    storage, key, barrier = LocalProductImageStorage(tmp_path), generate_storage_key(), Barrier(2)
    payloads = (b"SYNTHETIC FIRST", b"SYNTHETIC SECOND")

    def publish(payload):
        barrier.wait(timeout=5)
        try:
            storage.save(key, payload)
            return True
        except FileExistsError:
            return False

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(publish, payload) for payload in payloads]
            outcomes = [future.result(timeout=10) for future in pending]
        assert outcomes.count(True) == 1
        assert storage.read(key) == payloads[outcomes.index(True)]
        assert list(storage.keys()) == [key]  # Losing temporary object was cleaned.
    finally:
        storage.delete(key)
