from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.phone_verification_code import PhoneVerificationCode


class PhoneVerificationCodeRepository:
    def create_code(
        self,
        session: Session,
        *,
        user_id: str,
        phone_number: str,
        code_hash: str,
        expires_at: datetime,
    ) -> PhoneVerificationCode:
        verification_code = PhoneVerificationCode(
            user_id=user_id,
            phone_number=phone_number,
            code_hash=code_hash,
            expires_at=expires_at,
        )
        session.add(verification_code)
        session.flush()
        return verification_code

    def get_by_id(self, session: Session, code_id: str) -> PhoneVerificationCode | None:
        return session.get(PhoneVerificationCode, code_id)

    def get_latest_for_user(
        self, session: Session, user_id: str, *, for_update: bool = False
    ) -> PhoneVerificationCode | None:
        statement = (
            select(PhoneVerificationCode)
            .where(PhoneVerificationCode.user_id == user_id)
            .order_by(PhoneVerificationCode.created_at.desc(), PhoneVerificationCode.id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def get_latest_for_phone(
        self, session: Session, phone_number: str, *, for_update: bool = False
    ) -> PhoneVerificationCode | None:
        statement = (
            select(PhoneVerificationCode)
            .where(PhoneVerificationCode.phone_number == phone_number)
            .order_by(PhoneVerificationCode.created_at.desc(), PhoneVerificationCode.id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def count_created_since(self, session: Session, phone_number: str, since: datetime) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(PhoneVerificationCode)
                .where(
                    PhoneVerificationCode.phone_number == phone_number,
                    PhoneVerificationCode.created_at >= since,
                )
            )
            or 0
        )

    def increment_attempts(self, session: Session, code_id: str) -> int:
        session.execute(
            update(PhoneVerificationCode)
            .where(PhoneVerificationCode.id == code_id)
            .values(attempts=PhoneVerificationCode.attempts + 1)
        )
        session.flush()
        value = session.scalar(
            select(PhoneVerificationCode.attempts).where(PhoneVerificationCode.id == code_id)
        )
        return int(value or 0)

    def mark_verified(self, code: PhoneVerificationCode, verified_at: datetime) -> None:
        code.verified_at = verified_at

    def expire_code(self, code: PhoneVerificationCode, expired_at: datetime) -> None:
        code.expires_at = expired_at
