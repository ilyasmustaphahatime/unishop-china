"""Exercise the tooling/TLS integration paths affected by security-only upgrades."""

import ssl

import certifi
from cachecontrol.caches import FileCache
from filelock import FileLock, Timeout
import pytest


def test_certifi_bundle_loads_with_certificate_and_hostname_validation() -> None:
    context = ssl.create_default_context(cafile=certifi.where())
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.cert_store_stats()["x509_ca"] > 0


def test_audit_cache_filelock_round_trip(tmp_path) -> None:
    cache = FileCache(tmp_path / "audit-cache")
    cache.set("synthetic-cache-key", b"synthetic-cache-value")
    assert cache.get("synthetic-cache-key") == b"synthetic-cache-value"
    cache.delete("synthetic-cache-key")
    assert cache.get("synthetic-cache-key") is None


def test_filelock_still_excludes_independent_holders(tmp_path) -> None:
    path = tmp_path / "synthetic.lock"
    with FileLock(path):
        with pytest.raises(Timeout):
            with FileLock(path, timeout=0):
                pytest.fail("A second holder entered the protected section")
    with FileLock(path, timeout=0):
        pass
