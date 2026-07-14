from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models import PasswordResetToken, User


class PasswordResetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def invalidate_unused_tokens(self, *, user: User, used_at: datetime) -> None:
        self.db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id)
            .where(PasswordResetToken.used_at.is_(None))
            .values(used_at=used_at)
        )

    def create_token(
        self,
        *,
        user: User,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        token = PasswordResetToken(
            user=user,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(token)
        self.db.flush()
        return token

    def get_token_for_update(self, token_hash: str) -> PasswordResetToken | None:
        return self.db.scalar(
            select(PasswordResetToken)
            .options(joinedload(PasswordResetToken.user))
            .where(PasswordResetToken.token_hash == token_hash)
            .with_for_update()
        )
