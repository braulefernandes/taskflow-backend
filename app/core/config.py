from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="TaskFlow API", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    environment: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="APP_DEBUG")
    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret_key: str = Field(default="change-me-in-local-env", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    password_reset_token_expire_minutes: int = Field(
        default=30,
        alias="PASSWORD_RESET_TOKEN_EXPIRE_MINUTES",
        gt=0,
    )
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    email_backend: Literal["development", "smtp"] = Field(
        default="development",
        alias="EMAIL_BACKEND",
    )
    email_from_address: str = Field(
        default="no-reply@taskflow.local",
        alias="EMAIL_FROM_ADDRESS",
    )
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_timeout_seconds: int = Field(default=10, alias="SMTP_TIMEOUT_SECONDS")
    backend_cors_origins: str = Field(default="", alias="BACKEND_CORS_ORIGINS")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def cors_origins(self) -> list[str]:
        origins = [
            origin.strip()
            for origin in self.backend_cors_origins.split(",")
            if origin.strip()
        ]
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)
        return origins

    @property
    def password_reset_url(self) -> str:
        return f"{self.frontend_url.rstrip('/')}/redefinir-senha"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
