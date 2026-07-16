import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import OrganizationRole
from app.schemas.auth import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class MemberCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr = Field(max_length=320)
    role: OrganizationRole
    temporary_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if isinstance(value, str):
            return " ".join(value.strip().split())
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("temporary_password")
    @classmethod
    def validate_temporary_password(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Senha inválida.")
        return value


class MemberRoleUpdateRequest(BaseModel):
    role: OrganizationRole


class MemberStatusUpdateRequest(BaseModel):
    is_active: bool


class MemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: EmailStr
    role: OrganizationRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MemberListResponse(BaseModel):
    items: list[MemberResponse]
    total: int
    page: int
    page_size: int
