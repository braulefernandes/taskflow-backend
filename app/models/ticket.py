from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.ticket_enums import TicketPriority, TicketStatus

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.organization import Organization
    from app.models.ticket_comment import TicketComment
    from app.models.ticket_history import TicketHistory
    from app.models.user import User


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_organization_id", "organization_id"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_priority", "priority"),
        Index("ix_tickets_category_id", "category_id"),
        Index("ix_tickets_assignee_id", "assignee_id"),
        Index("ix_tickets_due_date", "due_date"),
        Index("ix_tickets_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(
            TicketStatus,
            name="ticket_status",
            values_callable=lambda statuses: [status.value for status in statuses],
            validate_strings=True,
        ),
        nullable=False,
        default=TicketStatus.PENDING,
        server_default=TicketStatus.PENDING.value,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(
            TicketPriority,
            name="ticket_priority",
            values_callable=lambda priorities: [
                priority.value for priority in priorities
            ],
            validate_strings=True,
        ),
        nullable=False,
        default=TicketPriority.MEDIUM,
        server_default=TicketPriority.MEDIUM.value,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    requester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    due_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="tickets")
    category: Mapped[Category] = relationship(back_populates="tickets")
    requester: Mapped[User] = relationship(
        back_populates="requested_tickets", foreign_keys=[requester_id]
    )
    assignee: Mapped[User | None] = relationship(
        back_populates="assigned_tickets", foreign_keys=[assignee_id]
    )
    comments: Mapped[list[TicketComment]] = relationship(
        back_populates="ticket", passive_deletes=True
    )
    history: Mapped[list[TicketHistory]] = relationship(
        back_populates="ticket", passive_deletes=True
    )
