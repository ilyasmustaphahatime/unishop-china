"""Shared identity budgets preserve the actual peer and domain-specific errors."""
import secrets
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Request
from pydantic import SecretStr

from app.api.rate_limits import enforce_authenticated_limit
from app.core.rate_limit import RateLimitDecision


def request(secret):
    return Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(
        settings=SimpleNamespace(jwt_secret_key=secret))), "client": ("127.0.0.1", 12345),
        "headers": [(b"x-forwarded-for", b"203.0.113.42")]})


def apply(request, peer, user, rejected, namespace="test"):
    enforce_authenticated_limit(request, "synthetic-user", ip_limiter=peer,
                                user_limiter=user, namespace=namespace, on_rejected=rejected)


def test_budget_uses_actual_peer_and_private_domain_separated_identity():
    req = request(SecretStr(secrets.token_urlsafe(32)))
    peer, user, rejected = Mock(), Mock(), Mock()
    peer.consume.return_value = user.consume.return_value = RateLimitDecision(True)
    apply(req, peer, user, rejected, "profile")
    first = user.consume.call_args.args[0]
    apply(req, peer, user, rejected, "seller")
    assert peer.consume.call_args.args == ("127.0.0.1",)
    assert first != user.consume.call_args.args[0]
    assert "synthetic-user" not in first
    rejected.assert_not_called()


def test_peer_rejection_stops_before_identity_budget():
    peer, user = Mock(), Mock()
    peer.consume.return_value = RateLimitDecision(False, 17)
    rejected = Mock(side_effect=ValueError("domain rejection"))
    with pytest.raises(ValueError, match="domain rejection"):
        apply(request(None), peer, user, rejected)
    rejected.assert_called_once_with(17)
    user.consume.assert_not_called()


def test_user_rejection_preserves_retry_after():
    peer, user = Mock(), Mock()
    peer.consume.return_value = RateLimitDecision(True)
    user.consume.return_value = RateLimitDecision(False, 23)
    rejected = Mock(side_effect=ValueError("domain rejection"))
    with pytest.raises(ValueError, match="domain rejection"):
        apply(request(SecretStr(secrets.token_urlsafe(32))), peer, user, rejected)
    rejected.assert_called_once_with(23)


def test_missing_signing_secret_fails_closed_before_identity_budget():
    peer, user = Mock(), Mock()
    peer.consume.return_value = RateLimitDecision(True)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is not configured"):
        apply(request(None), peer, user, Mock())
    user.consume.assert_not_called()
