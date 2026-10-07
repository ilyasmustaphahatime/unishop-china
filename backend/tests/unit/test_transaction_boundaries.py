"""Owned service transactions must finish or recover their request Session."""
from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from app.services.email_verification_service import EmailVerificationService
from app.services.password_change_service import PasswordChangeService
from app.services.refresh_session_service import RefreshSessionService

OWNERS = [EmailVerificationService, PasswordChangeService, RefreshSessionService]


@pytest.mark.parametrize("service", OWNERS)
def test_owned_auth_transaction_recovers_after_failed_commit(service):
    session = Mock()
    session.in_transaction.return_value = True
    session.begin_nested.return_value = nullcontext()
    session.commit.side_effect = RuntimeError("synthetic commit failure")
    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        with service._transaction(session):
            pass
    session.rollback.assert_called_once_with()


@pytest.mark.parametrize("service", OWNERS)
@pytest.mark.parametrize("already_read", [True, False])
def test_owned_auth_transaction_has_one_commit_owner(service, already_read):
    session = Mock()
    session.in_transaction.return_value = already_read
    session.begin_nested.return_value = nullcontext()
    session.begin.return_value = nullcontext()
    with service._transaction(session):
        pass
    if already_read:
        session.begin_nested.assert_called_once_with()
        session.commit.assert_called_once_with()
        session.begin.assert_not_called()
    else:
        session.begin.assert_called_once_with()
        session.commit.assert_not_called()  # Session.begin owns this commit.
        session.begin_nested.assert_not_called()
    session.rollback.assert_not_called()
