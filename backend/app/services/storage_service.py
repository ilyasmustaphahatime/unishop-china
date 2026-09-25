"""Private development storage; object-store adapters implement the same contract."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import RLock
import hashlib
import hmac
import os
import re
import secrets
import time
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000


class UnsafeEvidence(ValueError):
    pass


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    mime_type: str
    file_hash: str


def sanitize_image(data: bytes, filename: str, mime_type: str) -> CleanImage:
    """Decode only PNG/JPEG and rebuild pixels, discarding metadata/trailing content."""
    if not data or len(data) > MAX_BYTES:
        raise UnsafeEvidence("Image must be between 1 byte and 5 MiB.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,110}\.(?:jpg|jpeg|png)", filename, re.I):
        raise UnsafeEvidence("Use a simple JPEG or PNG filename.")
    extension = filename.rsplit(".", 1)[1].lower()
    expected = "PNG" if extension == "png" else "JPEG"
    if mime_type != ("image/png" if expected == "PNG" else "image/jpeg"):
        raise UnsafeEvidence("Image type does not match.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=["PNG", "JPEG"]) as image:
                if image.format != expected or getattr(image, "n_frames", 1) != 1:
                    raise UnsafeEvidence("Only single-frame JPEG and PNG images are accepted.")
                if image.width * image.height > MAX_PIXELS or max(image.size) > 6000:
                    raise UnsafeEvidence("Image dimensions are too large.")
                image.verify()
            with Image.open(BytesIO(data), formats=["PNG", "JPEG"]) as image:
                image.load()
                transformed = ImageOps.exif_transpose(image).convert("RGB")
                # Fresh image removes EXIF, embedded text, ICC profiles and comments.
                clean = Image.new("RGB", transformed.size)
                clean.paste(transformed)
                output = BytesIO()
                clean.save(output, format=expected)
                result = output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise UnsafeEvidence("Invalid or unsafe image.") from exc
    if len(result) > MAX_BYTES:
        raise UnsafeEvidence("Decoded image is too large.")
    return CleanImage(result, mime_type, hashlib.sha256(result).hexdigest())


class StorageProvider(ABC):
    @abstractmethod
    def upload(self, data: bytes) -> str: ...
    @abstractmethod
    def delete(self, key: str) -> None: ...
    @abstractmethod
    def read(self, key: str) -> bytes: ...
    @abstractmethod
    def generate_signed_url(self, key: str, *, actor_id: str, reference: str,
                            evidence_type: str, prefix: str) -> str: ...
    @abstractmethod
    def redeem(self, ticket: str, actor_id: str) -> tuple[str, str, str]: ...


class LocalPrivateStorage(StorageProvider):
    """Single-process local-only adapter. No static directory mount or public URL."""
    def __init__(self, root: Path, *, clock=time.monotonic):
        self.root = root.absolute()
        self.clock = clock
        self.secret = secrets.token_bytes(32)
        self.lock = RLock()
        self.tickets: dict[str, tuple] = {}

    def _root(self):
        for parent in (self.root, *self.root.parents):
            if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
                raise UnsafeEvidence("Private storage unavailable.")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, key: str) -> Path:
        if re.fullmatch(r"[a-f0-9]{64}", key) is None:
            raise UnsafeEvidence("Private storage unavailable.")
        self._root()
        path = self.root / key
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise UnsafeEvidence("Private storage unavailable.")
        return path

    def upload(self, data: bytes) -> str:
        key = secrets.token_hex(32)
        path = self._path(key)
        created = False
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
        except Exception:
            if created:
                path.unlink(missing_ok=True)
            raise
        return key

    def read(self, key: str) -> bytes:
        with self._path(key).open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise UnsafeEvidence("Private storage unavailable.")
        return data

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def generate_signed_url(self, key: str, *, actor_id: str, reference: str,
                            evidence_type: str, prefix: str) -> str:
        with self.lock:
            self.tickets = {k: v for k, v in self.tickets.items() if v[0] > self.clock()}
            if len(self.tickets) >= 1000:
                raise UnsafeEvidence("Private download capacity exceeded.")
            nonce = secrets.token_hex(32)
            signature = hmac.new(self.secret, nonce.encode(), hashlib.sha256).hexdigest()
            self.tickets[nonce] = (self.clock() + 60, actor_id, key, reference, evidence_type)
            return f"{prefix}/seller-verification/evidence/content?ticket={nonce}.{signature}"

    def redeem(self, ticket: str, actor_id: str) -> tuple[str, str, str]:
        if re.fullmatch(r"[a-f0-9]{64}\.[a-f0-9]{64}", ticket) is None:
            raise UnsafeEvidence("Evidence not available.")
        nonce, signature = ticket.split(".")
        expected = hmac.new(self.secret, nonce.encode(), hashlib.sha256).hexdigest()
        with self.lock:
            item = self.tickets.get(nonce)
            if (not hmac.compare_digest(signature, expected) or item is None
                    or item[0] <= self.clock() or item[1] != actor_id):
                raise UnsafeEvidence("Evidence not available.")
            self.tickets.pop(nonce)
            return item[2], item[3], item[4]
