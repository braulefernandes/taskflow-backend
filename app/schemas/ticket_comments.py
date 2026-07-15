import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TicketCommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class TicketCommentAuthorResponse(BaseModel):
    id: uuid.UUID
    name: str
    avatar_url: str | None

    model_config = ConfigDict(from_attributes=True)


class TicketCommentResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    content: str
    author: TicketCommentAuthorResponse
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
