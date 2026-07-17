from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def get_by_email(self, session: Session, email: str) -> User | None:
        return session.scalar(select(User).where(User.email == email))

    def get_by_phone(self, session: Session, phone_number: str) -> User | None:
        return session.scalar(select(User).where(User.phone_number == phone_number))

    def create(
        self,
        session: Session,
        *,
        email: str | None,
        phone_number: str | None,
        password_hash: str,
    ) -> User:
        user = User(email=email, phone_number=phone_number, password_hash=password_hash)
        session.add(user)
        session.flush()
        return user
