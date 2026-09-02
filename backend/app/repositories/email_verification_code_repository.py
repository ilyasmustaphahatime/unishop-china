from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.email_verification_code import EmailVerificationCode


class EmailVerificationCodeRepository:
    def create_pending(
        self,
        session: Session,
        *,
        user_id: str,
        code_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> EmailVerificationCode:
        challenge = EmailVerificationCode(
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
            attempts=0,
            activated_at=None,
            used_at=None,
            created_at=created_at,
        )
        session.add(challenge)
        session.flush()
        return challenge

    def get_latest_created_for_user(
        self,
        session: Session,
        user_id: str,
        *,
        for_update: bool = False,
    ) -> EmailVerificationCode | None:
        statement = (
            select(EmailVerificationCode)
            .where(EmailVerificationCode.user_id == user_id)
            .order_by(
                EmailVerificationCode.created_at.desc(),
                EmailVerificationCode.id.desc(),
            )
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def get_latest_active_for_user(
        self,
        session: Session,
        user_id: str,
        *,
        for_update: bool = False,
    ) -> EmailVerificationCode | None:
        statement = (
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.activated_at.is_not(None),
                EmailVerificationCode.used_at.is_(None),
            )
            .order_by(
                EmailVerificationCode.created_at.desc(),
                EmailVerificationCode.id.desc(),
            )
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
                .select_from(EmailVerificationCode)
                .where(
                    EmailVerificationCode.user_id == user_id,
                    EmailVerificationCode.created_at >= since,
                )
            )
            or 0
        )

    def get_oldest_created_since(
        self,
        session: Session,
        *,
        user_id: str,
        since: datetime,
    ) -> datetime | None:
        return session.scalar(
            select(EmailVerificationCode.created_at)
            .where(
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.created_at >= since,
            )
            .order_by(EmailVerificationCode.created_at.asc())
            .limit(1)
        )

    def activate_pending(
        self,
        session: Session,
        *,
        code_id: str,
        user_id: str,
        now: datetime,
    ) -> int:
        statement = (
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.id == code_id,
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.activated_at.is_(None),
                EmailVerificationCode.used_at.is_(None),
                EmailVerificationCode.expires_at > now,
            )
            .values(activated_at=now)
            .execution_options(synchronize_session="fetch")
        )
        return int(session.execute(statement).rowcount or 0)

    def cancel_pending(
        self,
        session: Session,
        *,
        code_id: str,
        user_id: str,
        now: datetime,
    ) -> int:
        statement = (
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.id == code_id,
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.activated_at.is_(None),
                EmailVerificationCode.used_at.is_(None),
            )
            .values(used_at=now)
            .execution_options(synchronize_session="fetch")
        )
        return int(session.execute(statement).rowcount or 0)

    def invalidate_active_for_user(
        self,
        session: Session,
        *,
        user_id: str,
        now: datetime,
        exclude_code_id: str | None = None,
    ) -> int:
        conditions = [
            EmailVerificationCode.user_id == user_id,
            EmailVerificationCode.activated_at.is_not(None),
            EmailVerificationCode.used_at.is_(None),
        ]
        if exclude_code_id is not None:
            conditions.append(EmailVerificationCode.id != exclude_code_id)
        statement = (
            update(EmailVerificationCode)
            .where(*conditions)
            .values(used_at=now)
            .execution_options(synchronize_session="fetch")
        )
        return int(session.execute(statement).rowcount or 0)

    def increment_attempts_if_available(
        self,
        session: Session,
        *,
        code_id: str,
        user_id: str,
        now: datetime,
        maximum_attempts: int,
    ) -> int:
        statement = (
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.id == code_id,
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.activated_at.is_not(None),
                EmailVerificationCode.used_at.is_(None),
                EmailVerificationCode.expires_at > now,
                EmailVerificationCode.attempts < maximum_attempts,
            )
            .values(attempts=EmailVerificationCode.attempts + 1)
            .execution_options(synchronize_session="fetch")
        )
        return int(session.execute(statement).rowcount or 0)

    def consume_if_available(
        self,
        session: Session,
        *,
        code_id: str,
        user_id: str,
        now: datetime,
        maximum_attempts: int,
    ) -> int:
        statement = (
            update(EmailVerificationCode)
            .where(
                EmailVerificationCode.id == code_id,
                EmailVerificationCode.user_id == user_id,
                EmailVerificationCode.activated_at.is_not(None),
                EmailVerificationCode.used_at.is_(None),
                EmailVerificationCode.expires_at > now,
                EmailVerificationCode.attempts < maximum_attempts,
            )
            .values(used_at=now)
            .execution_options(synchronize_session="fetch")
        )
        return int(session.execute(statement).rowcount or 0)
