import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    pass


class EmailSender(Protocol):
    def send_password_reset(
        self,
        *,
        to_email: str,
        reset_url: str,
        expires_minutes: int,
    ) -> None: ...


class DevelopmentEmailSender:
    def send_password_reset(
        self,
        *,
        to_email: str,
        reset_url: str,
        expires_minutes: int,
    ) -> None:
        del to_email, reset_url, expires_minutes
        logger.info("Password reset email suppressed by development adapter.")


class SmtpEmailSender:
    def __init__(self, email_settings: Settings) -> None:
        self.settings = email_settings

    def send_password_reset(
        self,
        *,
        to_email: str,
        reset_url: str,
        expires_minutes: int,
    ) -> None:
        if not self.settings.smtp_host:
            raise EmailDeliveryError("SMTP is not configured.")

        message = EmailMessage()
        message["Subject"] = "Redefinição de senha - TaskFlow"
        message["From"] = self.settings.email_from_address
        message["To"] = to_email
        message.set_content(
            "Use o link abaixo para redefinir sua senha. "
            f"Ele expira em {expires_minutes} minutos.\n\n{reset_url}"
        )

        try:
            with smtplib.SMTP(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=self.settings.smtp_timeout_seconds,
            ) as smtp:
                if self.settings.smtp_use_tls:
                    smtp.starttls()
                if self.settings.smtp_username and self.settings.smtp_password:
                    smtp.login(
                        self.settings.smtp_username,
                        self.settings.smtp_password.get_secret_value(),
                    )
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Password reset email delivery failed.") from exc


def get_email_sender() -> EmailSender:
    if settings.email_backend.lower() == "smtp":
        return SmtpEmailSender(settings)
    return DevelopmentEmailSender()
