from datetime import datetime

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
