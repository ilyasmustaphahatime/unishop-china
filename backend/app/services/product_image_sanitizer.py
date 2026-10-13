"""Bounded static raster decoding; no evidence policy or filename trust."""
from dataclasses import dataclass
from io import BytesIO
from threading import BoundedSemaphore
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.common.product_image_rules import (
    CHUNK_BYTES, MAX_DIMENSION, MAX_PIXELS, MAX_RAW_BYTES, MAX_STORED_BYTES, MIME_TYPES,
)

decode_slots = BoundedSemaphore(2)


class UnsafeProductImage(ValueError):
    pass


class ImageProcessingBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class SanitizedProductImage:
    data: bytes
    mime_type: str
    width: int
    height: int


def bounded_image_read(stream) -> bytes:
    data = bytearray()
    while True:
        chunk = stream.read(min(CHUNK_BYTES, MAX_RAW_BYTES + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_RAW_BYTES:
            raise UnsafeProductImage("Image exceeds 10 MiB.")
    if not data:
        raise UnsafeProductImage("Image is empty.")
    return bytes(data)


def validate_dimensions(width: int, height: int):
    if min(width, height) <= 0 or max(width, height) > MAX_DIMENSION or width * height > MAX_PIXELS:
        raise UnsafeProductImage("Image dimensions exceed limits.")


def _container(data: bytes, format: str):
    """Reject trailing payloads; decoding/rebuilding also discards embedded metadata."""
    if format == "WEBP":
        if data[:4] != b"RIFF" or data[8:12] != b"WEBP" or int.from_bytes(data[4:8], "little") + 8 != len(data):
            raise UnsafeProductImage("Invalid image container.")
    elif format == "PNG":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise UnsafeProductImage("Invalid image container.")
        offset = 8
        while offset + 12 <= len(data):
            length = int.from_bytes(data[offset:offset + 4], "big")
            kind = data[offset + 4:offset + 8]
            offset += length + 12
            if offset > len(data):
                break
            if kind == b"IEND" and length == 0 and offset == len(data):
                return
            if kind == b"IEND":
                break
        raise UnsafeProductImage("Invalid image container.")
    elif format == "JPEG":
        if not data.startswith(b"\xff\xd8"):
            raise UnsafeProductImage("Invalid image container.")
        offset = 2
        for _ in range(100000):
            if offset + 2 > len(data) or data[offset] != 255:
                break
            while offset < len(data) and data[offset] == 255:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker == 0xD9:
                if offset == len(data):
                    return
                break
            if marker in {0xD8, 0x00}:
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset:offset + 2], "big")
            if length < 2 or offset + length > len(data):
                break
            offset += length
            if marker == 0xDA:
                # Scan entropy markers, honoring stuffed FF00/restart/fill bytes.
                while True:
                    next_marker = data.find(b"\xff", offset)
                    if next_marker < 0 or next_marker + 1 >= len(data):
                        offset = len(data)
                        break
                    value = data[next_marker + 1]
                    if value == 0 or 0xD0 <= value <= 0xD7:
                        offset = next_marker + 2
                    elif value == 255:
                        offset = next_marker + 1
                    else:
                        offset = next_marker
                        break
        raise UnsafeProductImage("Invalid image container.")


def sanitize_product_image(data: bytes) -> SanitizedProductImage:
    if not data or len(data) > MAX_RAW_BYTES:
        raise UnsafeProductImage("Image must be between 1 byte and 10 MiB.")
    if not decode_slots.acquire(blocking=False):
        raise ImageProcessingBusy("Image processing capacity unavailable.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=list(MIME_TYPES)) as image:
                format = image.format
                if format not in MIME_TYPES or getattr(image, "n_frames", 1) != 1 or getattr(image, "is_animated", False):
                    raise UnsafeProductImage("Only static JPEG, PNG and WebP are accepted.")
                validate_dimensions(image.width, image.height)
                _container(data, format)
                image.verify()
            with Image.open(BytesIO(data), formats=list(MIME_TYPES)) as image:
                image.load()
                with ImageOps.exif_transpose(image) as oriented:
                    mode = "RGB" if format == "JPEG" or not ("A" in oriented.getbands() or "transparency" in oriented.info) else "RGBA"
                    with oriented.convert(mode) as converted, Image.new(mode, converted.size) as clean:
                        clean.paste(converted)
                        output = BytesIO()
                        options = {"quality": 95, "subsampling": 0} if format == "JPEG" else {"lossless": True} if format == "WEBP" else {}
                        clean.save(output, format=format, **options)
                        result, (width, height) = output.getvalue(), clean.size
        if not result or len(result) > MAX_STORED_BYTES:
            raise UnsafeProductImage("Sanitized image exceeds 10 MiB.")
        return SanitizedProductImage(result, MIME_TYPES[format], width, height)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise UnsafeProductImage("Invalid or unsafe product image.") from error
    finally:
        decode_slots.release()
