import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from urllib.parse import urlencode

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.security import get_password_hash
from app.models import PasswordResetToken
from app.repositories.password_reset import PasswordResetRepository
from app.schemas.password_reset import ForgotPasswordRequest, ResetPasswordRequest
from app.services.email import EmailSender

logger = logging.getLogger(__name__)

FORGOT_PASSWORD_MESSAGE = (
    "Se o e-mail estiver cadastrado, enviaremos instrucoes para redefinir a senha."
)
RESET_PASSWORD_MESSAGE = "Senha redefinida com sucesso."
TOKEN_BYTES = 32


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PasswordResetService:
    def __init__(
        self,
        db: Session,
        email_sender: EmailSender | None = None,
        repository: PasswordResetRepository | None = None,
    ) -> None:
        self.db = db
        self.email_sender = email_sender
        self.repository = repository or PasswordResetRepository(db)

    def request_reset(self, payload: ForgotPasswordRequest) -> str:
        user = self.repository.get_user_by_email(str(payload.email))
        if user is None or not user.is_active:
            return FORGOT_PASSWORD_MESSAGE

        plain_token = secrets.token_urlsafe(TOKEN_BYTES)
        now = datetime.now(UTC)
        expires_minutes = settings.password_reset_token_expire_minutes
        reset_url = f"{settings.password_reset_url}?{urlencode({'token': plain_token})}"

        try:
            if self.email_sender is None:
                raise RuntimeError("Password reset email sender is not configured.")
            self.repository.invalidate_unused_tokens(user=user, used_at=now)
            self.repository.create_token(
                user=user,
                token_hash=hash_reset_token(plain_token),
                expires_at=now + timedelta(minutes=expires_minutes),
            )
            self.email_sender.send_password_reset(
                to_email=user.email,
                reset_url=reset_url,
                expires_minutes=expires_minutes,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.error("Password reset request could not be processed.")

        return FORGOT_PASSWORD_MESSAGE

    def reset_password(self, payload: ResetPasswordRequest) -> str:
        try:
            now = datetime.now(UTC)
            reset_token = self.repository.get_token_for_update(
                hash_reset_token(payload.token)
            )
            if not self._is_valid(reset_token, now):
                raise invalid_reset_token_error()

            assert reset_token is not None
            reset_token.user.password_hash = get_password_hash(payload.new_password)
            reset_token.used_at = now
            self.db.commit()
            return RESET_PASSWORD_MESSAGE
        except AppException:
            self.db.rollback()
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise AppException(
                "Nao foi possivel redefinir a senha.",
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="password_reset_persistence_error",
            ) from exc
        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def _is_valid(
        reset_token: PasswordResetToken | None,
        now: datetime,
    ) -> bool:
        if reset_token is None or reset_token.used_at is not None:
            return False
        expires_at = reset_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return (
            expires_at > now
            and reset_token.user is not None
            and reset_token.user.is_active
        )


def invalid_reset_token_error() -> AppException:
    return AppException(
        "Token de redefinicao invalido ou expirado.",
        status_code=HTTPStatus.BAD_REQUEST,
        code="invalid_reset_token",
    )
