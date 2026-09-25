"""Run a local HTTP/MySQL security smoke audit with exact synthetic cleanup.

Launches a private loopback Uvicorn process with memory-only fake providers.
Never contacts a real delivery provider, prints credentials, or alters real users.
"""

from pathlib import Path
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def snapshot(engine):
    from sqlalchemy import MetaData, Table, select

    result = {}
    with engine.connect() as connection:
        metadata = MetaData()
        for name in (
            "users", "user_roles", "phone_verification_codes", "refresh_tokens",
            "password_reset_codes", "email_verification_codes", "user_profiles",
            "seller_verifications", "seller_evidence", "seller_verification_audit",
        ):
            table = Table(name, metadata, autoload_with=connection)
            rows = connection.execute(select(table).order_by(table.c.id)).all()
            payload = json.dumps([[str(v) if v is not None else None for v in row]
                                  for row in rows], separators=(",", ":"), ensure_ascii=False)
            result[name] = (len(rows), hashlib.sha256(payload.encode()).hexdigest())
    return result


def main() -> int:
    import httpx
    from sqlalchemy import delete, select
    from sqlalchemy.orm import Session
    import app.models  # noqa: F401
    from app.core.config import settings
    from app.core.database import engine
    from app.common.enums import AccountStatus
    from app.models import User, UserRole
    from app.common.enums import UserRoleType
    from io import BytesIO
    from PIL import Image

    if settings.app_env.strip().lower() != "development" or engine.url.host not in {
        "127.0.0.1", "localhost", "::1",
    }:
        print("HTTP audit refused: a local development database is required.")
        return 1
    baseline = snapshot(engine)
    marker = uuid4().hex
    emails = [f"pre7-http-{marker}-{i}@example.com" for i in range(2)]
    passwords = [secrets.token_urlsafe(32) + "Aa1" for _ in range(3)]
    phone = "+86138" + "".join(str(secrets.randbelow(10)) for _ in range(8))
    with Session(engine) as session:
        if session.scalar(select(User.id).where(User.phone_number == phone)):
            print("HTTP audit refused: synthetic identifier collision.")
            return 1
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    env = os.environ.copy()
    private_storage = tempfile.TemporaryDirectory(prefix="unishop-seller-http-")
    assert Path(private_storage.name).resolve().parent == Path(tempfile.gettempdir()).resolve()
    env.update({
        "APP_ENV": "development", "APP_DEBUG": "false",
        "SMS_ENABLED": "true", "SMS_PROVIDER": "fake",
        "ENABLE_FAKE_SMS_DEV_INBOX": "true", "FAKE_SMS_DELIVERY_DELAY_SECONDS": "0",
        "PASSWORD_RESET_DELIVERY_PROVIDER": "fake",
        "ENABLE_FAKE_PASSWORD_RESET_DEV_INBOX": "true",
        "FAKE_PASSWORD_RESET_DELIVERY_DELAY_SECONDS": "0",
        "EMAIL_VERIFICATION_DELIVERY_PROVIDER": "fake",
        "ENABLE_FAKE_EMAIL_VERIFICATION_DEV_INBOX": "true",
        "FAKE_EMAIL_VERIFICATION_DELIVERY_DELAY_SECONDS": "0",
        "REFRESH_COOKIE_SECURE": "false",
        "SELLER_PRIVATE_STORAGE_DIR": private_storage.name,
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--no-proxy-headers", "--no-access-log"],
        cwd=BACKEND_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    passed = []
    stage = "startup"

    def check(ok, label):
        if not ok:
            raise AssertionError(label)
        passed.append(label)

    try:
        base_url = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base_url, timeout=15) as first, \
                httpx.Client(base_url=base_url, timeout=15) as second:
            for _ in range(100):
                try:
                    if first.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Startup unavailable")
            stage = "health"
            for path in ("/", "/health", "/api/v1/health", "/api/v1/health/database"):
                check(first.get(path).status_code == 200, "health:" + path)
            for i, client in enumerate((first, second)):
                stage = "registration"
                payload = {"email": emails[i], "password": passwords[0]}
                if i == 0:
                    payload["phone_number"] = phone
                check(client.post("/api/v1/auth/register", json=payload).status_code == 201,
                      f"register:{i}")
                stage = "login"
                response = client.post("/api/v1/auth/login", json={
                    "identifier": emails[i], "password": passwords[0],
                })
                check(response.status_code == 200, f"login:{i}")
                client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
                check(response.headers.get("cache-control") == "no-store", f"no-store:{i}")
                cookies = response.headers.get_list("set-cookie")
                check(any("HttpOnly" in c and "Path=/api/v1/auth" in c
                          and "SameSite=lax" in c for c in cookies), f"cookie-scope:{i}")
            stage = "verification"
            check(first.get("/api/v1/auth/me").status_code == 200, "auth-me")
            code = first.post("/api/v1/dev/fake-sms/latest", json={"phone_number": phone})
            check(code.status_code == 200, "fake-phone-delivery")
            check(first.post("/api/v1/auth/phone/verify", json={
                "phone_number": phone, "code": code.json()["code"],
            }).status_code == 200, "phone-verify")
            check(first.post("/api/v1/auth/email/resend-code", json={}).status_code == 202,
                  "email-resend")
            code = first.get("/api/v1/dev/fake-email/latest")
            check(code.status_code == 200, "fake-email-delivery")
            check(first.post("/api/v1/auth/email/verify", json={
                "code": code.json()["code"],
            }).status_code == 200, "email-verify")
            stage = "profiles"
            profile = first.get("/api/v1/profile/me")
            check(profile.status_code == 200, "lazy-profile")
            check(profile.headers.get("cache-control") == "no-store", "private-profile-no-store")
            public_handle = profile.json()["public_handle"]
            public_path = "/api/v1/profiles/by-handle/" + public_handle
            check(second.get(public_path).status_code == 404, "incomplete-profile-hidden")
            check(first.post("/api/v1/profile/onboarding/complete", json={}).status_code == 409,
                  "incomplete-onboarding-rejected")
            check(first.patch("/api/v1/profile/me", json={
                "display_name": "Audit Member", "city": "Qingdao",
                "bio": "<img src=x onerror=alert(1)>",
            }).status_code == 200, "update-profile")
            check(first.post("/api/v1/profile/onboarding/complete", json={}).status_code == 200,
                  "complete-onboarding")
            public = second.get(public_path)
            check(public.status_code == 200 and set(public.json()) == {
                "public_handle", "display_name", "bio", "city", "member_since",
                "email_verified", "phone_verified",
            }, "public-minimal-contract")
            check(public.json()["bio"] == "<img src=x onerror=alert(1)>", "plain-text-contract")
            for account_status in (AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED):
                with Session(engine) as session, session.begin():
                    synthetic_user = session.scalar(select(User).where(User.email == emails[0]))
                    synthetic_user.account_status = account_status
                check(second.get(public_path).status_code == 404,
                      "hidden-profile:" + account_status.value)
            with Session(engine) as session, session.begin():
                synthetic_user = session.scalar(select(User).where(User.email == emails[0]))
                synthetic_user.account_status = AccountStatus.ACTIVE
            check(second.patch("/api/v1/profile/me", json={
                "public_handle": public_handle, "bio": "Cross-user mutation",
            }).status_code == 422, "cross-user-mass-assignment-rejected")
            stage = "password-reset"
            seller = "/api/v1/seller-verification"
            started = first.post(seller, json={"action": "start"})
            check(started.status_code == 200, "seller-draft")
            reference = started.json()["review_reference"]
            buffer = BytesIO()
            Image.new("RGB", (16, 16), "blue").save(buffer, "PNG")
            for kind in ("SELFIE", "WECHAT_PROOF", "HANDWRITTEN_CODE"):
                uploaded = first.post(seller + "/evidence", data={"evidence_type": kind},
                                      files={"file": ("proof.png", buffer.getvalue(), "image/png")})
                check(uploaded.status_code == 200, "seller-upload:" + kind)
            check(first.post(seller, json={"action": "submit"}).status_code == 200, "seller-submit")
            access_body = {"review_reference": reference, "evidence_type": "SELFIE"}
            check(second.post(seller + "/evidence/access", json=access_body).status_code == 404,
                  "seller-evidence-owner-boundary")
            access = first.post(seller + "/evidence/access", json=access_body)
            check(access.status_code == 200, "seller-private-access-grant")
            download = first.get(access.json()["url"])
            check(download.status_code == 200 and download.headers.get("cache-control") == "no-store",
                  "seller-private-download")
            check(first.get(access.json()["url"]).status_code == 422, "seller-download-replay")
            admin_path = "/api/v1/admin/seller-verifications"
            check(second.get(admin_path).status_code == 403, "seller-admin-boundary")
            with Session(engine) as session, session.begin():
                synthetic_admin = session.scalar(select(User).where(User.email == emails[1]))
                session.add(UserRole(user_id=synthetic_admin.id, role=UserRoleType.ADMIN))
            check(second.get(admin_path).status_code == 200, "seller-admin-queue")
            reviewed = second.post(admin_path + "/" + reference + "/approve", json={})
            check(reviewed.status_code == 200 and reviewed.json()["status"] == "VERIFIED", "seller-approval")
            check(first.post(seller + "/evidence", data={"evidence_type": "SELFIE"},
                             files={"file": ("proof.png", buffer.getvalue(), "image/png")}).status_code == 409,
                  "seller-evidence-immutable-after-review")
            check(first.post("/api/v1/auth/password/forgot", json={
                "identifier": emails[0],
            }).status_code == 202, "forgot")
            code = first.post("/api/v1/dev/fake-password-reset/latest", json={
                "identifier": emails[0],
            })
            check(code.status_code == 200, "fake-reset-delivery")
            reset_payload = {"identifier": emails[0], "code": code.json()["code"],
                             "new_password": passwords[1]}
            check(first.post("/api/v1/auth/password/reset", json=reset_payload).status_code == 200,
                  "reset")
            check(first.post("/api/v1/auth/password/reset", json=reset_payload).status_code == 400,
                  "reset-replay-rejected")
            first.headers["X-CSRF-Token"] = first.cookies.get(settings.csrf_cookie_name)
            check(first.post("/api/v1/auth/refresh").status_code == 401, "reset-revokes-session")
            response = first.post("/api/v1/auth/login", json={
                "identifier": emails[0], "password": passwords[1],
            })
            check(response.status_code == 200, "login-after-reset")
            first.headers["Authorization"] = "Bearer " + response.json()["access_token"]
            stage = "password-change"
            check(first.post("/api/v1/auth/password/change", json={
                "current_password": passwords[1], "new_password": passwords[2],
            }).status_code == 200, "password-change")
            check(not first.cookies.get(settings.refresh_cookie_name), "password-change-clears-cookie")
            response = first.post("/api/v1/auth/login", json={
                "identifier": emails[0], "password": passwords[2],
            })
            check(response.status_code == 200, "login-after-change")
            first.headers["Authorization"] = "Bearer " + response.json()["access_token"]
            check(first.get("/api/v1/profile/me").json()["onboarding_completed"],
                  "onboarding-server-persistence")
            stage = "logout"
            check(first.post("/api/v1/auth/logout-all").status_code == 204, "logout-all")
            check(first.post("/api/v1/auth/refresh").status_code == 401, "logout-all-refresh-rejected")
            second.headers["X-CSRF-Token"] = second.cookies.get(settings.csrf_cookie_name)
            check(second.post("/api/v1/auth/refresh").status_code == 200, "other-user-session-preserved")
            second.headers["X-CSRF-Token"] = second.cookies.get(settings.csrf_cookie_name)
            check(second.post("/api/v1/auth/logout").status_code == 204, "logout")
            check(second.post("/api/v1/auth/refresh").status_code == 401, "logout-refresh-rejected")
        result = 0
    except Exception as error:
        print(json.dumps({"status": "FAIL", "stage": stage, "error_type": type(error).__name__}))
        result = 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        with Session(engine) as session, session.begin():
            session.execute(delete(User).where(User.email.in_(emails)))
        private_storage.cleanup()
        preserved = snapshot(engine) == baseline
        print(json.dumps({"checks_passed": passed, "preservation": preserved,
                          "synthetic_cleanup": preserved, "server_stopped": process.poll() is not None}))
        if not preserved:
            result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
