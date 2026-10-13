"""Narrow product-media object interface. No DB or authorization decisions."""
from abc import ABC, abstractmethod
from pathlib import Path
import logging
import os
import re
import secrets

from app.common.product_image_rules import MAX_STORED_BYTES, STORAGE_KEY_PATTERN

logger = logging.getLogger(__name__)


class ProductImageStorage(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes) -> None: ...
    @abstractmethod
    def read(self, key: str) -> bytes: ...
    @abstractmethod
    def delete(self, key: str) -> None: ...
    @abstractmethod
    def keys(self): ...

    def exists(self, key: str) -> bool:
        try:
            self.read(key)
            return True
        except FileNotFoundError:
            return False


class LocalProductImageStorage(ProductImageStorage):
    def __init__(self, root: Path):
        self.root = root.absolute()

    @staticmethod
    def _check_components(path):
        for component in (path, *path.parents):
            if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
                raise OSError("Product storage unavailable.")

    def _path(self, key: str, *, create=False):
        if re.fullmatch(STORAGE_KEY_PATTERN, key) is None:
            raise OSError("Product storage unavailable.")
        self._check_components(self.root)
        directory = self.root / "product-media"
        self._check_components(directory)
        if create:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / key
        self._check_components(path)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise OSError("Product storage unavailable.")
        return path

    def save(self, key: str, data: bytes):
        if not data or len(data) > MAX_STORED_BYTES:
            raise OSError("Product storage unavailable.")
        path = self._path(key, create=True)
        temporary = path.parent / (".pending-" + secrets.token_hex(16))
        published = False
        temporary_created = False
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            temporary_created = True
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # Atomic exclusive publication of completed bytes; no overwrite.
            os.link(temporary, path, follow_symlinks=False)
            published = True
            temporary.unlink()
        except Exception:
            for owned in ([path, temporary] if published else [temporary] if temporary_created else []):
                try:
                    owned.unlink(missing_ok=True)
                except OSError:
                    logger.error("PRODUCT_IMAGE_INCOMPLETE_SAVE_CLEANUP_FAILED")
            raise

    def read(self, key: str) -> bytes:
        descriptor = os.open(self._path(key), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            data = stream.read(MAX_STORED_BYTES + 1)
        if not data or len(data) > MAX_STORED_BYTES:
            raise OSError("Product storage unavailable.")
        return data

    def delete(self, key: str):
        self._path(key).unlink(missing_ok=True)

    def keys(self):
        directory = self._path("product-media/" + "0" * 64).parent
        if not directory.exists():
            return
        for path in directory.iterdir():
            self._check_components(path)
            # Report-only auditing also detects abandoned temporary objects.
            if path.is_file():
                yield "product-media/" + path.name


class DisabledProductImageStorage(ProductImageStorage):
    def save(self, key, data):
        raise OSError("Product storage provider is not configured.")
    def read(self, key):
        raise OSError("Product storage provider is not configured.")
    def delete(self, key):
        raise OSError("Product storage provider is not configured.")
    def keys(self):
        raise OSError("Product storage provider is not configured.")


def product_image_storage(config):
    # Development-only local adapter; a future cloud adapter replaces the factory.
    if config.app_env.lower() != "development" or config.product_image_storage_provider != "local":
        return DisabledProductImageStorage()
    product = (config.product_image_storage_dir / "product-media").resolve()
    evidence = config.seller_private_storage_dir.resolve()
    if product.is_relative_to(evidence) or evidence.is_relative_to(product):
        return DisabledProductImageStorage()
    return LocalProductImageStorage(config.product_image_storage_dir)
