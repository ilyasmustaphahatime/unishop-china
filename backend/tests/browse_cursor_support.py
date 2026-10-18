"""Ephemeral dedicated cursor key for production-mode application tests."""
import secrets

TEST_BROWSE_CURSOR_KEY = secrets.token_urlsafe(48)
