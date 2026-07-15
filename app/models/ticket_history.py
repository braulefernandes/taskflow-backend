from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.ticket_history_action import TicketHistoryAction

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketHistory(Base):
    """Audit entry whose producer must redact secrets before storing values."""

    __tablename__ = "ticket_history"
    __table_args__ = (
        CheckConstraint(
            "old_value IS NULL OR length(old_value) <= 2000",
            name="old_value_length",
        ),
        CheckConstraint(
            "new_value IS NULL OR length(new_value) <= 2000",
            name="new_value_length",
        ),
        Index("ix_ticket_history_ticket_id_created_at", "ticket_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[TicketHistoryAction] = mapped_column(
        Enum(
            TicketHistoryAction,
            name="ticket_history_action",
            values_callable=lambda actions: [action.value for action in actions],
            validate_strings=True,
        ),
        nullable=False,
    )
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    ticket: Mapped[Ticket] = relationship(back_populates="history")
    user: Mapped[User] = relationship(back_populates="ticket_history")
