from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def get_by_id(self, session: Session, user_id: str) -> User | None:
        return session.scalar(select(User).where(User.id == user_id))

    def get_by_id_for_update(self, session: Session, user_id: str) -> User | None:
        return session.scalar(select(User).where(User.id == user_id).with_for_update())

    def get_by_email(self, session: Session, email: str) -> User | None:
        return session.scalar(select(User).where(User.email == email))

    def get_by_phone(
        self, session: Session, phone_number: str, *, for_update: bool = False
    ) -> User | None:
        statement = select(User).where(User.phone_number == phone_number)
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def mark_phone_verified(self, user: User) -> None:
        user.phone_verified = True

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
