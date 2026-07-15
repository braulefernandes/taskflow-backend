import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import TicketPriority, TicketStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


def normalize_required_text(value: str) -> str:
    return " ".join(value.strip().split())


class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    category_id: uuid.UUID
    priority: TicketPriority
    due_date: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        if isinstance(value, str):
            return normalize_required_text(value)
        return value


class TicketUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    category_id: uuid.UUID | None = None
    priority: TicketPriority | None = None
    due_date: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Campo obrigatorio nao pode ser nulo.")
        if isinstance(value, str):
            return normalize_required_text(value)
        return value

    @field_validator("category_id", "priority", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Campo obrigatorio nao pode ser nulo.")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "TicketUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para atualizar.")
        return self


class TicketAssigneeUpdateRequest(BaseModel):
    assignee_id: uuid.UUID | None

    model_config = ConfigDict(extra="forbid")


class TicketStatusUpdateRequest(BaseModel):
    status: TicketStatus

    model_config = ConfigDict(extra="forbid")


class OrganizationSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    model_config = ConfigDict(from_attributes=True)


class CategorySummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    model_config = ConfigDict(from_attributes=True)


class UserSummary(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    avatar_url: str | None
    model_config = ConfigDict(from_attributes=True)


class TicketResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    due_date: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    organization: OrganizationSummary
    category: CategorySummary
    requester: UserSummary
    assignee: UserSummary | None
    is_overdue: bool = False
    overdue_seconds: int = 0
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def calculate_overdue(self) -> "TicketResponse":
        if self.due_date is None or self.status in {
            TicketStatus.COMPLETED,
            TicketStatus.CANCELLED,
        }:
            self.is_overdue = False
            self.overdue_seconds = 0
            return self

        due_date = (
            self.due_date
            if self.due_date.tzinfo is not None
            else self.due_date.replace(tzinfo=UTC)
        )
        seconds = int((utc_now() - due_date.astimezone(UTC)).total_seconds())
        self.is_overdue = seconds > 0
        self.overdue_seconds = max(seconds, 0)
        return self


class TicketListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[TicketResponse]
