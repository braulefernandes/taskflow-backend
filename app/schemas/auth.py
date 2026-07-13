import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.roles import OrganizationRole

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class RegisterRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=255, examples=["Ana Silva"])
    email: EmailStr = Field(max_length=320, examples=["ana@example.com"])
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        examples=["Senha123"],
    )
    organization_name: str = Field(min_length=1, max_length=255, examples=["Acme Suporte"])

    @field_validator("user_name", "organization_name", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        has_letter = bool(re.search(r"[A-Za-z]", value))
        has_number = bool(re.search(r"\d", value))
        if not has_letter or not has_number:
            raise ValueError("Senha invalida.")
        return value


class UserPublic(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    avatar_url: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationPublic(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MembershipPublic(BaseModel):
    id: uuid.UUID
    role: OrganizationRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegisterResponse(BaseModel):
    user: UserPublic
    organization: OrganizationPublic
    membership: MembershipPublic


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=320, examples=["ana@example.com"])
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH, examples=["Senha123"])

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
