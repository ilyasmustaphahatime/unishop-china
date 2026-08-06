from datetime import datetime

from sqlalchemy import distinct, func, select, update
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def create_refresh_session(
        self,
        session: Session,
        *,
        user_id: str,
        token_hash: str,
        family_id: str,
        csrf_token_hash: str,
        expires_at: datetime,
        family_expires_at: datetime,
    ) -> RefreshToken:
        record = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            csrf_token_hash=csrf_token_hash,
            expires_at=expires_at,
            family_expires_at=family_expires_at,
        )
        session.add(record)
        session.flush()
        return record

    def get_for_update_by_hash(
        self,
        session: Session,
        token_hash: str,
    ) -> RefreshToken | None:
        statement = (
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
        return session.scalar(statement)

    def token_hash_exists(self, session: Session, token_hash: str) -> bool:
        return session.scalar(
            select(RefreshToken.id).where(RefreshToken.token_hash == token_hash).limit(1)
        ) is not None

    def count_active_families(
        self,
        session: Session,
        *,
        user_id: str,
        now: datetime,
    ) -> int:
        statement = select(func.count(distinct(RefreshToken.family_id))).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
            RefreshToken.family_expires_at > now,
        )
        return int(session.scalar(statement) or 0)

    def get_oldest_active_family(
        self,
        session: Session,
        *,
        user_id: str,
        now: datetime,
    ) -> str | None:
        statement = (
            select(RefreshToken.family_id)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
                RefreshToken.family_expires_at > now,
            )
            .order_by(RefreshToken.created_at, RefreshToken.id)
            .limit(1)
            .with_for_update()
        )
        return session.scalar(statement)

    def mark_token_rotated(
        self,
        token: RefreshToken,
        *,
        replacement_id: str,
        now: datetime,
    ) -> None:
        token.revoked_at = now
        token.revocation_reason = "rotated"
        token.replaced_by_token_id = replacement_id
        token.last_used_at = now

    def revoke_family(
        self,
        session: Session,
        *,
        family_id: str,
        reason: str,
        now: datetime,
        include_revoked: bool = False,
    ) -> int:
        conditions = [RefreshToken.family_id == family_id]
        if not include_revoked:
            conditions.append(RefreshToken.revoked_at.is_(None))
        statement = (
            update(RefreshToken)
            .where(*conditions)
            .values(revoked_at=now, revocation_reason=reason, last_used_at=now)
        )
        return int(session.execute(statement).rowcount or 0)

    def revoke_all_for_user(
        self,
        session: Session,
        *,
        user_id: str,
        reason: str,
        now: datetime,
    ) -> int:
        statement = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason=reason, last_used_at=now)
        )
        return int(session.execute(statement).rowcount or 0)
