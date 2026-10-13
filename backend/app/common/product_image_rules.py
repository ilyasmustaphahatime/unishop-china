"""Product-media limits and opaque references; separate from identity evidence."""
import re
import secrets
from typing import Annotated

from pydantic import AfterValidator, Field

MAX_IMAGES = 8
MAX_RAW_BYTES = 10 * 1024 * 1024
MAX_STORED_BYTES = MAX_RAW_BYTES
MAX_DIMENSION = 6000
MAX_PIXELS = 30_000_000
CHUNK_BYTES = 64 * 1024
MAX_MULTIPART_BYTES = MAX_RAW_BYTES + CHUNK_BYTES
IMAGE_REF_PATTERN = r"^img-[0-9a-f]{32}$"
STORAGE_KEY_PATTERN = r"^product-media/[0-9a-f]{64}$"
MIME_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def generate_image_ref() -> str:
    return "img-" + secrets.token_hex(16)


def generate_storage_key() -> str:
    return "product-media/" + secrets.token_hex(32)


def validate_image_ref(value: str) -> str:
    if re.fullmatch(IMAGE_REF_PATTERN, value) is None:
        raise ValueError("Invalid image reference.")
    return value


ImageRef = Annotated[str, Field(strict=True, max_length=36, pattern=IMAGE_REF_PATTERN),
                     AfterValidator(validate_image_ref)]
