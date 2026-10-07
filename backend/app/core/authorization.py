"""Authoritative role checks reusable inside a service-owned transaction."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus, UserRoleType
from app.models import UserRole
from app.repositories.user_repository import UserRepository


class AuthorizationError(Exception):
    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def lock_active_user(db: Session, user_id: str, *, eligible=False):
    user = UserRepository().get_by_id_for_update(db, user_id)
    if user is None or user.account_status != AccountStatus.ACTIVE:
        raise AuthorizationError("Account unavailable.", 401)
    if eligible and (not user.email_verified or not user.phone_verified):
        raise AuthorizationError("Verify both email and phone before continuing.", 403)
    return user


def require_db_admin(db: Session, actor_id: str):
    role = db.scalar(select(UserRole.id).where(
        UserRole.user_id == actor_id, UserRole.role == UserRoleType.ADMIN).with_for_update())
    if role is None:
        raise AuthorizationError("Administrator access required.", 403)
