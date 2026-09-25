from functools import lru_cache
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.profiles.dependencies import _enforce_authenticated_limit
from app.common.enums import UserRoleType
from app.core.database import get_db
from app.core.config import BACKEND_DIR
from app.core.rate_limit import InMemoryRateLimiter
from app.models import UserRole
from app.services.auth_service import SafeAuthenticatedUser
from app.services.seller_verification_service import SellerVerificationService
from app.services.storage_service import LocalPrivateStorage

limiters = {name: (InMemoryRateLimiter(max_requests=count * 3, window_seconds=60, max_keys=10000),
                  InMemoryRateLimiter(max_requests=count, window_seconds=60, max_keys=10000))
            for name, count in {"submission": 5, "upload": 12, "admin": 30, "read": 60}.items()}


def limited(name):
    def dependency(request: Request, user: SafeAuthenticatedUser = Depends(get_current_user)):
        ip_limiter, user_limiter = limiters[name]
        try:
            _enforce_authenticated_limit(request, user, ip_limiter=ip_limiter, user_limiter=user_limiter,
                                         namespace="seller-" + name)
        except HTTPException as exc:
            if exc.status_code == 429:
                raise HTTPException(429, "Too many verification requests. Please try again later.",
                                    headers=exc.headers) from None
            raise
        return user
    return dependency


submission_user = limited("submission")
upload_user = limited("upload")
read_user = limited("read")
admin_user = limited("admin")


def require_admin(user=Depends(admin_user), db: Session = Depends(get_db)):
    if db.scalar(select(UserRole.id).where(UserRole.user_id == user.id,
                                          UserRole.role == UserRoleType.ADMIN)) is None:
        raise HTTPException(403, "Administrator access required.")
    return user


@lru_cache(maxsize=4)
def local_storage(path):
    return LocalPrivateStorage(path)


def get_seller_service(request: Request):
    config = request.app.state.settings
    if config.app_env.lower() != "development":
        # No production local-disk fallback. Install a private object-store adapter first.
        raise HTTPException(503, "Seller evidence storage is not configured.")
    path = config.seller_private_storage_dir.resolve()
    if path.is_relative_to(BACKEND_DIR.parent) and not path.is_relative_to(BACKEND_DIR / "private_uploads"):
        raise HTTPException(503, "Seller evidence storage must be private.")
    return SellerVerificationService(local_storage(config.seller_private_storage_dir))
