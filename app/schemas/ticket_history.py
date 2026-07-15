import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import TicketHistoryAction


class TicketHistoryAuthorResponse(BaseModel):
    id: uuid.UUID
    name: str
    avatar_url: str | None

    model_config = ConfigDict(from_attributes=True)


class TicketHistoryResponse(BaseModel):
    id: uuid.UUID
    action: TicketHistoryAction
    field_name: str | None
    old_value: str | None
    new_value: str | None
    author: TicketHistoryAuthorResponse = Field(validation_alias="user")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
