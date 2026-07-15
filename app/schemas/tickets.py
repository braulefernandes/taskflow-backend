import uuid
from datetime import UTC, datetime
from enum import Enum
from math import ceil

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


class TicketSortBy(str, Enum):
    CREATED_AT = "created_at"
    DUE_DATE = "due_date"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class TicketListFilters(BaseModel):
    search: str | None = Field(default=None, max_length=255)
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    overdue: bool | None = None
    sort_by: TicketSortBy = TicketSortBy.CREATED_AT
    sort_order: SortOrder = SortOrder.DESC
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("search", mode="before")
    @classmethod
    def trim_search(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @model_validator(mode="after")
    def validate_periods(self) -> "TicketListFilters":
        for start_name, end_name in (
            ("created_from", "created_to"),
            ("due_from", "due_to"),
        ):
            start = getattr(self, start_name)
            end = getattr(self, end_name)
            if start is not None and end is not None:
                if normalize_filter_datetime(start) > normalize_filter_datetime(end):
                    raise ValueError(
                        f"{start_name} deve ser anterior ou igual a {end_name}."
                    )
        return self


def normalize_filter_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC)


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
    total_pages: int
    items: list[TicketResponse]

    @classmethod
    def build(
        cls,
        *,
        filters: TicketListFilters,
        total: int,
        items: list[TicketResponse],
    ) -> "TicketListResponse":
        return cls(
            page=filters.page,
            page_size=filters.page_size,
            total=total,
            total_pages=ceil(total / filters.page_size),
            items=items,
        )
