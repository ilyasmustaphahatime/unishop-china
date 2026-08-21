from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.password_reset_code import PasswordResetCode


class PasswordResetCodeRepository:
    def get_latest_for_user(
        self,
        session: Session,
        user_id: str,
        *,
        for_update: bool = False,
    ) -> PasswordResetCode | None:
        statement = (
            select(PasswordResetCode)
            .where(PasswordResetCode.user_id == user_id)
            .order_by(PasswordResetCode.created_at.desc(), PasswordResetCode.id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def count_created_since(
        self,
        session: Session,
        *,
        user_id: str,
        since: datetime,
    ) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(PasswordResetCode)
                .where(
                    PasswordResetCode.user_id == user_id,
                    PasswordResetCode.created_at >= since,
                )
            )
            or 0
        )

    def invalidate_active_for_user(
        self,
        session: Session,
        *,
        user_id: str,
        now: datetime,
    ) -> int:
        statement = (
            update(PasswordResetCode)
            .where(
                PasswordResetCode.user_id == user_id,
                PasswordResetCode.used_at.is_(None),
                PasswordResetCode.expires_at > now,
            )
            .values(used_at=now)
            .execution_options(synchronize_session="fetch")
        )
        return int(session.execute(statement).rowcount or 0)

    def create_pending(
        self,
        session: Session,
        *,
        user_id: str,
        code_hash: str,
        expires_at: datetime,
        pending_at: datetime,
    ) -> PasswordResetCode:
        record = PasswordResetCode(
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
            used_at=pending_at,
            created_at=pending_at,
        )
        session.add(record)
        session.flush()
        return record

    def activate_pending(
        self,
        session: Session,
        *,
        code_id: str,
    ) -> int:
        statement = (
            update(PasswordResetCode)
            .where(
                PasswordResetCode.id == code_id,
                PasswordResetCode.used_at.is_not(None),
            )
            .values(used_at=None)
            .execution_options(synchronize_session="fetch")
        )
        return int(session.execute(statement).rowcount or 0)
