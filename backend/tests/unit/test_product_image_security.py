from io import BytesIO
from pathlib import Path
import asyncio
import struct
import zlib

from PIL import Image
from PIL.TiffImagePlugin import IFDRational
import pytest

from app.common.product_image_rules import MAX_RAW_BYTES, generate_image_ref, generate_storage_key, validate_image_ref
from app.core.http_input import bounded_spooled_body
from app.services.product_image_sanitizer import (
    bounded_image_read, sanitize_product_image, validate_dimensions, UnsafeProductImage, ImageProcessingBusy,
)
from app.services.product_image_storage import LocalProductImageStorage, DisabledProductImageStorage, product_image_storage
from app.core.config import settings
from tests.product_image_fixtures import raster


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_static_formats_are_reencoded_with_authoritative_type(format):
    original = raster(format)
    clean = sanitize_product_image(original)
    assert clean.mime_type == {"JPEG":"image/jpeg", "PNG":"image/png", "WEBP":"image/webp"}[format]
    assert (clean.width, clean.height) == (12, 8)
    with Image.open(BytesIO(clean.data)) as decoded:
        decoded.load()
        assert decoded.format == format and getattr(decoded, "n_frames", 1) == 1 and not decoded.getexif()
        pixel = decoded.convert("RGB").getpixel((0, 0))
        assert all(abs(actual - expected) <= 3 for actual, expected in zip(pixel, (30, 80, 120)))


@pytest.mark.parametrize("format", ["PNG", "WEBP"])
def test_alpha_is_preserved_without_metadata(format):
    clean = sanitize_product_image(raster(format, alpha=True))
    with Image.open(BytesIO(clean.data)) as decoded:
        assert decoded.convert("RGBA").getpixel((0,0)) == (30,80,120,90)
        assert not decoded.info.get("exif") and not decoded.info.get("icc_profile")


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_orientation_and_synthetic_exif_are_removed(format):
    exif = Image.Exif()
    exif[274] = 6
    exif[271] = "SYNTHETIC CAMERA"
    exif[306] = "2001:01:01 00:00:00"
    exif[34853] = {1:"N", 2: (IFDRational(10,1), IFDRational(20,1), IFDRational(30,1))}
    original = raster(format, size=(6,4), exif=exif)
    with Image.open(BytesIO(original)) as source:
        assert source.getexif().get_ifd(34853)
    clean = sanitize_product_image(original)
    assert (clean.width, clean.height) == (4,6)
    with Image.open(BytesIO(clean.data)) as output:
        assert not output.getexif()
        assert b"SYNTHETIC CAMERA" not in clean.data and b"2001:01:01" not in clean.data


@pytest.mark.parametrize("payload", [b"", b"MZ executable", b"<html>private</html>", b"<svg></svg>",
    b"%PDF-1.7", b"PK archive", b"random bytes", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff",
    b"RIFF\x04\x00\x00\x00WEBP"])
def test_non_image_and_corrupt_signatures_fail(payload):
    with pytest.raises(UnsafeProductImage):
        sanitize_product_image(payload)


@pytest.mark.parametrize("format", ["GIF", "BMP", "TIFF", "ICO"])
def test_unsupported_decodable_formats_fail(format):
    with pytest.raises(UnsafeProductImage):
        sanitize_product_image(raster(format, size=(16,16)))


@pytest.mark.parametrize("format", ["PNG", "WEBP", "GIF"])
def test_animation_is_rejected(format):
    with pytest.raises(UnsafeProductImage):
        sanitize_product_image(raster(format, animated=True))


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_truncation_and_concatenated_polyglot_are_rejected(format):
    data = raster(format)
    for payload in (data[:-8], data + b"<script>attack</script>", data + data):
        with pytest.raises(UnsafeProductImage):
            sanitize_product_image(payload)


@pytest.mark.parametrize("width,height,allowed", [
    (1,1,True), (6000,5000,True), (5000,6000,True), (6000,1,True),
    (0,1,False), (1,0,False), (6001,1,False), (1,6001,False), (6000,6000,False),
])
def test_dimension_boundaries_without_large_allocations(width, height, allowed):
    if allowed:
        validate_dimensions(width,height)
    else:
        with pytest.raises(UnsafeProductImage):
            validate_dimensions(width,height)


@pytest.mark.parametrize("width,height", [(6001,1), (1,6001), (6000,6000)])
def test_oversize_header_rejected_before_decompression(width,height):
    data = bytearray(raster())
    data[16:24] = struct.pack(">II", width,height)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    with pytest.raises(UnsafeProductImage):
        sanitize_product_image(bytes(data))


@pytest.mark.parametrize("threshold", [10, 0])
def test_pillow_bomb_warning_and_error_remain_active(monkeypatch, threshold):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", threshold)
    with pytest.raises(UnsafeProductImage):
        sanitize_product_image(raster(size=(4,4)))
    assert Image.MAX_IMAGE_PIXELS == threshold


def test_reads_are_always_bounded_and_raw_limit_is_actual_bytes():
    class Stream(BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 65536
            return super().read(size)
    assert bounded_image_read(Stream(b"small")) == b"small"
    with pytest.raises(UnsafeProductImage):
        bounded_image_read(Stream(b"x" * (MAX_RAW_BYTES + 1)))


def test_decoder_capacity_failure_is_safe(monkeypatch):
    class Busy:
        def acquire(self, *, blocking):
            assert not blocking
            return False
    monkeypatch.setattr("app.services.product_image_sanitizer.decode_slots", Busy())
    with pytest.raises(ImageProcessingBusy):
        sanitize_product_image(raster())


@pytest.mark.parametrize("key", ["../secret", "product-media/../secret", "product-media/"+"a"*64+"/x",
    "product-media/../../seller-evidence/x", "C:\\secret", "/secret", "%2e%2e/secret", "product-media/"+"A"*64])
def test_storage_key_traversal_is_rejected_without_creating_root(tmp_path,key):
    root = tmp_path / "uncreated"
    storage = LocalProductImageStorage(root)
    for operation in (lambda: storage.save(key,b"data"), lambda: storage.read(key), lambda: storage.delete(key)):
        with pytest.raises(OSError, match="Product storage unavailable"):
            operation()
    assert not root.exists()


def test_atomic_storage_is_immutable_and_audit_is_read_only(tmp_path):
    storage = LocalProductImageStorage(tmp_path / "media")
    assert list(storage.keys()) == [] and not storage.root.exists()
    key = generate_storage_key()
    try:
        storage.save(key,b"original")
        with pytest.raises(FileExistsError):
            storage.save(key,b"different")
        assert storage.read(key) == b"original"
        assert list(storage.keys()) == [key]
    finally:
        storage.delete(key)
    assert list(storage.keys()) == []


def test_atomic_publish_failure_cleans_owned_temporary_file(tmp_path, monkeypatch):
    storage = LocalProductImageStorage(tmp_path)
    def fail(*args,**kwargs):
        raise OSError("synthetic publication failure")
    monkeypatch.setattr("app.services.product_image_storage.os.link", fail)
    with pytest.raises(OSError):
        storage.save(generate_storage_key(),b"data")
    assert list(storage.keys()) == []


def test_preexisting_temporary_file_is_not_deleted_on_name_collision(tmp_path,monkeypatch):
    storage = LocalProductImageStorage(tmp_path)
    path = tmp_path / "product-media" / (".pending-" + "a"*32)
    path.parent.mkdir()
    path.write_bytes(b"preexisting synthetic sentinel")
    monkeypatch.setattr("app.services.product_image_storage.secrets.token_hex", lambda _: "a"*32)
    try:
        with pytest.raises(FileExistsError):
            storage.save("product-media/"+"b"*64,b"data")
        assert path.read_bytes() == b"preexisting synthetic sentinel"
    finally:
        path.unlink()


@pytest.mark.parametrize("kind", ["symlink","junction"])
def test_linked_storage_components_are_denied(tmp_path, monkeypatch, kind):
    storage = LocalProductImageStorage(tmp_path)
    method = "is_symlink" if kind == "symlink" else "is_junction"
    monkeypatch.setattr(Path, method, lambda path: path == tmp_path, raising=False)
    with pytest.raises(OSError):
        storage.save(generate_storage_key(),b"data")


def test_refs_random_bounded_and_not_client_identity():
    refs = {generate_image_ref() for _ in range(500)}
    assert len(refs) == 500 and all(validate_image_ref(ref) == ref and len(ref) == 36 for ref in refs)
    for ref in ("../x", "img-"+"A"*32, "img-"+"a"*32+"\n"):
        with pytest.raises(ValueError):
            validate_image_ref(ref)


def test_production_and_evidence_overlapping_roots_fail_closed(tmp_path):
    prod = settings.model_copy(update={"app_env":"production"})
    assert isinstance(product_image_storage(prod),DisabledProductImageStorage)
    overlap = settings.model_copy(update={"product_image_storage_dir":tmp_path,
        "seller_private_storage_dir":tmp_path/"product-media"/"evidence"})
    assert isinstance(product_image_storage(overlap),DisabledProductImageStorage)


def test_spooled_body_bounds_chunks_timeout_disconnect_and_cleanup():
    async def run():
        messages = iter([{"type":"http.request","body":b"abc","more_body":True},
                         {"type":"http.request","body":b"def","more_body":False}])
        async def receive():
            return next(messages)
        async with bounded_spooled_body(receive,maximum_bytes=6) as body:
            assert body.read() == b"abcdef"
        assert body.closed
        async def too_large():
            return {"type":"http.request","body":b"1234567"}
        with pytest.raises(ValueError):
            async with bounded_spooled_body(too_large,maximum_bytes=6):
                pytest.fail("oversized body was accepted")
        async def disconnect():
            return {"type":"http.disconnect"}
        with pytest.raises(ConnectionError):
            async with bounded_spooled_body(disconnect,maximum_bytes=6):
                pytest.fail("disconnect was accepted")
        async def slow():
            await asyncio.sleep(0.1)
        with pytest.raises(TimeoutError):
            async with bounded_spooled_body(slow,maximum_bytes=6,timeout_seconds=0.01):
                pytest.fail("slow body was accepted")
    asyncio.run(run())
