"""Adversarial regressions for the final Phase 6 security gate.

Persistent tests own exact random user IDs and remove only those rows.
Credentials and challenge values remain in memory and are never logged.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import RequestVerificationError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_password, verify_password
from app.core.session_security import validate_request_origin
from app.integrations.password_reset_delivery import PasswordResetDeliveryResult
from app.main import create_app
from app.models import PasswordResetCode, RefreshToken, User
from app.schemas.auth import LoginRequest
from app.services.auth_service import AuthenticationService
from app.services.password_change_service import PasswordChangeService
from app.services.password_reset_service import PasswordResetRequestService
from app.services.refresh_session_service import RefreshSessionService
from app.services.token_service import AccessTokenService
from app.common.enums import AccountStatus
from app.models import UserProfile


@pytest.fixture(autouse=True)
def isolated_login_budget():
    from app.api.v1.auth.dependencies import (
        login_ip_rate_limiter, login_identifier_rate_limiter, registration_rate_limiter,
    )
    for limiter in (login_ip_rate_limiter, login_identifier_rate_limiter, registration_rate_limiter):
        limiter.clear()
    yield
    for limiter in (login_ip_rate_limiter, login_identifier_rate_limiter, registration_rate_limiter):
        limiter.clear()


@pytest.fixture
def owned_user():
    user_id = str(uuid4())
    password = secrets.token_urlsafe(32) + "Aa1"
    email = f"pre7-audit-{user_id}@example.com"
    with Session(engine) as session, session.begin():
        session.add(User(id=user_id, email=email, password_hash=hash_password(password)))
    try:
        yield user_id, email, password
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(User).where(User.id == user_id, User.email == email))


def test_login_racing_password_change_cannot_leave_old_credential_session(owned_user):
    user_id, email, password = owned_user
    verifying = Event()
    release = Event()
    changed = Event()

    def paused_verifier(submitted, digest):
        valid = verify_password(submitted, digest)
        verifying.set()
        assert release.wait(10)
        return valid

    def login():
        with Session(engine) as session:
            AuthenticationService(password_verifier=paused_verifier).authenticate_user_and_create_access_token(
                session, LoginRequest(identifier=email, password=password)
            )

    def change():
        with Session(engine) as session:
            PasswordChangeService().change_password(
                session, user_id=user_id, current_password=password,
                new_password=secrets.token_urlsafe(32) + "Bb2",
            )
        changed.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        login_future = pool.submit(login)
        if not verifying.wait(3):
            login_future.result(timeout=1)
            raise AssertionError("Login did not reach password verification.")
        change_future = pool.submit(change)
        # With correct serialization the changer waits for the login transaction.
        changed.wait(0.5)
        release.set()
        login_future.result(timeout=15)
        change_future.result(timeout=15)
    with Session(engine) as session:
        active = session.scalar(select(func.count()).select_from(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None),
        ))
        assert active == 0


def test_delayed_reset_delivery_cannot_activate_after_password_change(owned_user):
    user_id, email, password = owned_user

    class ChangeDuringDelivery:
        enabled = True
        available = True

        def deliver_reset_code(self, **_kwargs):
            with Session(engine) as session:
                PasswordChangeService().change_password(
                    session, user_id=user_id, current_password=password,
                    new_password=secrets.token_urlsafe(32) + "Bb2",
                )
            return PasswordResetDeliveryResult(delivered=True, provider="audit")

    with Session(engine) as session:
        PasswordResetRequestService(
            settings, delivery_provider=ChangeDuringDelivery(),
        ).request_reset(session, identifier=email, identifier_kind="email")
    with Session(engine) as session:
        challenge = session.scalar(select(PasswordResetCode).where(
            PasswordResetCode.user_id == user_id,
        ))
        assert challenge is not None
        assert challenge.used_at is not None


@pytest.mark.parametrize("suffix", ["/", "//", "/path", ".attacker.example", ":9", "?x=1"])
def test_origin_must_match_without_request_normalization(suffix):
    with pytest.raises(RequestVerificationError):
        validate_request_origin("http://localhost:5173" + suffix, settings)


@pytest.mark.parametrize("path", [
    "/api/v1/auth/me", "/api/v1/profile/me", "/api/v1/profile/onboarding/complete",
    "/api/v1/auth/phone/verify", "/api/v1/auth/phone/resend-code",
])
def test_private_api_failures_are_never_cacheable(path):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get(path) if path.endswith("/me") else client.post(path, json={})
    assert response.status_code in {401, 422}
    assert response.headers.get("cache-control") == "no-store"


def test_limiter_key_churn_cannot_reset_an_unexpired_budget():
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=2)
    assert limiter.consume("victim").allowed
    assert limiter.consume("other").allowed
    overflow = limiter.consume("new-key")
    assert not overflow.allowed
    assert overflow.retry_after_seconds and overflow.retry_after_seconds > 0
    assert not limiter.consume("victim").allowed


def test_logout_with_rotated_cookie_revokes_the_surviving_family(owned_user):
    user_id, _, _ = owned_user
    service = RefreshSessionService()
    with Session(engine) as session, session.begin():
        original = service.create_login_session(session, user_id=user_id)
    with Session(engine) as session:
        service.rotate_session(
            session, raw_refresh_token=original.refresh_token,
            csrf_cookie=original.csrf_token, csrf_header=original.csrf_token,
        )
    with Session(engine) as session:
        service.logout_current(
            session, raw_refresh_token=original.refresh_token,
            csrf_cookie=original.csrf_token, csrf_header=original.csrf_token,
        )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None),
        )) == 0


def test_phone_limit_counts_malformed_requests_and_ignores_forwarded_peer():
    from app.api.v1.auth.dependencies import phone_verification_ip_rate_limiter

    with TestClient(create_app(settings), client=("198.51.100.240", 1234)) as client:
        for _ in range(phone_verification_ip_rate_limiter.max_requests):
            assert client.post("/api/v1/auth/phone/verify", json={}).status_code == 422
        response = client.post("/api/v1/auth/phone/resend-code", json={}, headers={
            "X-Forwarded-For": "127.0.0.1", "Forwarded": "for=127.0.0.1",
        })
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


@pytest.mark.parametrize("account_status", list(AccountStatus))
def test_account_state_matrix_uses_current_database_authority(owned_user, account_status):
    user_id, email, password = owned_user
    token = AccessTokenService().create_access_token(user_id)
    public_id = str(uuid4())
    with Session(engine) as session, session.begin():
        user = session.get(User, user_id)
        user.account_status = account_status
        session.add(UserProfile(user_id=user_id, public_id=public_id, display_name="Audit User",
                                city="Qingdao", onboarding_completed=True))
    active = account_status is AccountStatus.ACTIVE
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        login = client.post("/api/v1/auth/login", json={"identifier": email, "password": password})
        assert login.status_code == (200 if active else 401)
        client.headers["Authorization"] = "Bearer " + token
        for path in ("/api/v1/auth/me", "/api/v1/profile/me"):
            response = client.get(path)
            assert response.status_code == (200 if active else 401)
            assert response.headers.get("cache-control") == "no-store"
        assert client.patch("/api/v1/profile/me", json={"bio": "Owned data"}).status_code == (
            200 if active else 401
        )
        assert client.post("/api/v1/profile/onboarding/complete", json={}).status_code == (
            200 if active else 401
        )
        assert client.get("/api/v1/profiles/" + public_id).status_code == (200 if active else 404)
        # These invalid challenges must never mutate verification or credentials.
        for path, payload in (
            ("/api/v1/auth/email/verify", {"code": "000000"}),
            ("/api/v1/auth/password/change", {"current_password": "WrongPassword1",
                                            "new_password": "AuditReplacement2"}),
        ):
            assert client.post(path, json=payload).status_code == (400 if active else 401)


POST_ENDPOINTS = (
    "/auth/register", "/auth/login", "/auth/refresh", "/auth/logout", "/auth/logout-all",
    "/auth/password/forgot", "/auth/password/reset", "/auth/password/change",
    "/auth/phone/resend-code", "/auth/phone/verify", "/auth/email/resend-code",
    "/auth/email/verify", "/profile/onboarding/complete",
)


@pytest.mark.parametrize("path", POST_ENDPOINTS)
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_unexpected_methods_do_not_enter_mutation_routes(path, method):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        assert client.request(method, "/api/v1" + path).status_code == 405


@pytest.mark.parametrize("path", ["/auth/register", "/auth/login", "/auth/password/reset",
                                  "/auth/phone/verify"])
@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded",
                                          "multipart/form-data"])
def test_json_mutations_reject_other_content_types(path, content_type):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.post("/api/v1" + path, content=b"{}", headers={
            "Content-Type": content_type,
        })
        assert response.status_code in {400, 415, 422}
        assert "input" not in response.text


@pytest.mark.parametrize("field", [
    "role", "roles", "admin", "is_admin", "status", "account_status", "email_verified",
    "phone_verified", "password_hash", "seller_verified", "user_id", "id", "created_at",
    "updated_at",
])
def test_registration_privileged_field_matrix_is_strict(field):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.post("/api/v1/auth/register", json={
            "email": "audit-never-created@example.com", "password": "AuditPassword1", field: "attack",
        })
    assert response.status_code == 422
    assert "attack" not in response.text


def test_cors_preflight_accepts_only_configured_origin():
    with TestClient(create_app(settings)) as client:
        for origin in ("http://localhost:5173.attacker.example", "null", "https://localhost:5173",
                       "http://localhost:5174", "http://localhost:5173/"):
            response = client.options("/api/v1/profile/me", headers={
                "Origin": origin, "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            })
            assert response.status_code == 400
            assert "access-control-allow-origin" not in response.headers
        response = client.options("/api/v1/profile/me", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        })
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_real_mysql_duplicate_registration_has_one_winner():
    from app.core.exceptions import RegistrationConflictError
    from app.schemas.auth import RegisterRequest
    from app.services.auth_service import RegistrationService
    from sqlalchemy.exc import OperationalError

    email = f"pre7-race-{uuid4().hex}@example.com"
    request = RegisterRequest(email=email, password=secrets.token_urlsafe(32) + "Aa1")
    barrier = Barrier(2)

    def register():
        barrier.wait(timeout=10)
        with Session(engine) as session:
            try:
                RegistrationService().register(session, request)
                return "created"
            except RegistrationConflictError:
                return "rejected"
            except OperationalError as error:
                assert error.orig.args[0] == 1213
                return "deadlock-rollback"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: register(), range(2)))
        assert outcomes.count("created") == 1
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(User).where(User.email == email)) == 1
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(User).where(User.email == email))


@pytest.mark.parametrize("valid", [False, True])
def test_phone_concurrent_verification_preserves_attempts_and_consumption(owned_user, valid):
    from datetime import timedelta
    from app.core.exceptions import PhoneVerificationError
    from app.core.security import generate_verification_code, hash_verification_code
    from app.integrations.sms_client import FakeSmsSender
    from app.models import PhoneVerificationCode
    from app.models.base import utc_now
    from app.services.phone_verification_service import PhoneVerificationService

    user_id, _, _ = owned_user
    phone = "+86138" + "".join(str(secrets.randbelow(10)) for _ in range(8))
    code = generate_verification_code()
    submitted = code if valid else str((int(code) + 1) % 1000000).zfill(6)
    with Session(engine) as session, session.begin():
        session.get(User, user_id).phone_number = phone
        session.add(PhoneVerificationCode(
            user_id=user_id, phone_number=phone,
            code_hash=hash_verification_code(code, settings.verification_code_hash_secret),
            expires_at=utc_now() + timedelta(minutes=10),
        ))
    service = PhoneVerificationService(
        sms_sender=FakeSmsSender(), verification_code_hash_secret=settings.verification_code_hash_secret,
    )
    barrier = Barrier(2)

    def verify():
        barrier.wait(timeout=10)
        with Session(engine) as session:
            try:
                service.verify(session, phone, submitted)
                return True
            except PhoneVerificationError:
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: verify(), range(2)))
    assert outcomes == [valid, valid]
    with Session(engine) as session:
        challenge = session.scalar(select(PhoneVerificationCode).where(
            PhoneVerificationCode.user_id == user_id,
        ))
        assert session.get(User, user_id).phone_verified is valid
        assert (challenge.verified_at is not None) is valid
        assert challenge.attempts == (0 if valid else 2)


def test_concurrent_phone_resend_creates_one_challenge(owned_user):
    from app.core.exceptions import PhoneVerificationError
    from app.integrations.sms_client import FakeSmsSender
    from app.models import PhoneVerificationCode
    from app.services.phone_verification_service import PhoneVerificationService

    user_id, _, _ = owned_user
    phone = "+86138" + "".join(str(secrets.randbelow(10)) for _ in range(8))
    with Session(engine) as session, session.begin():
        session.get(User, user_id).phone_number = phone
    service = PhoneVerificationService(
        sms_sender=FakeSmsSender(), verification_code_hash_secret=settings.verification_code_hash_secret,
    )
    barrier = Barrier(2)

    def resend():
        barrier.wait(timeout=10)
        with Session(engine) as session:
            try:
                service.resend(session, phone)
                return "sent"
            except PhoneVerificationError as error:
                assert error.status_code == 429
                return "limited"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: resend(), range(2)))
    assert sorted(outcomes) == ["limited", "sent"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PhoneVerificationCode).where(
            PhoneVerificationCode.user_id == user_id,
        )) == 1


@pytest.mark.parametrize("operation", ["create", "complete"])
def test_profile_creation_and_completion_rollback_on_flush_failure(owned_user, operation):
    from sqlalchemy import event
    from app.services.profile_service import ProfileService

    user_id, _, _ = owned_user
    if operation == "complete":
        with Session(engine) as session, session.begin():
            session.add(UserProfile(user_id=user_id, display_name="Ready User", city="Qingdao"))

    def fail_write(session, _context, _instances):
        for row in session.new.union(session.dirty):
            if isinstance(row, UserProfile):
                raise RuntimeError("Controlled profile persistence failure")

    with Session(engine) as session:
        event.listen(session, "before_flush", fail_write)
        with pytest.raises(RuntimeError, match="Controlled profile persistence failure"):
            if operation == "create":
                ProfileService().get_or_create_own(session, user_id=user_id)
            else:
                ProfileService().complete_onboarding(session, user_id=user_id)
    with Session(engine) as session:
        profile = session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
        if operation == "create":
            assert profile is None
        else:
            assert profile is not None and profile.onboarding_completed is False


def test_unhandled_private_failure_is_generic_and_not_cacheable():
    from app.api.v1.auth.dependencies import get_current_user

    config = settings.model_copy(update={"app_debug": False})
    app = create_app(config)

    def fail():
        raise RuntimeError("Sensitive diagnostic marker")

    app.dependency_overrides[get_current_user] = fail
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/profile/me")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers.get("cache-control") == "no-store"
