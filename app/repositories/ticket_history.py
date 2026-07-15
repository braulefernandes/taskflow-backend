import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Ticket, TicketHistory, TicketHistoryAction, User


class TicketHistoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_event(
        self,
        *,
        ticket: Ticket,
        user: User,
        action: TicketHistoryAction,
        field_name: str | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
    ) -> TicketHistory:
        created_at = datetime.now(UTC)
        latest_created_at = self.db.scalar(
            select(func.max(TicketHistory.created_at)).where(
                TicketHistory.ticket_id == ticket.id
            )
        )
        if latest_created_at is not None:
            latest_utc = (
                latest_created_at
                if latest_created_at.tzinfo is not None
                else latest_created_at.replace(tzinfo=UTC)
            )
            if created_at <= latest_utc:
                created_at = latest_utc + timedelta(microseconds=1)
        event = TicketHistory(
            ticket=ticket,
            user=user,
            action=action,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            created_at=created_at,
        )
        self.db.add(event)
        return event

    def list_events(self, *, ticket_id: uuid.UUID) -> list[TicketHistory]:
        statement = (
            select(TicketHistory)
            .options(joinedload(TicketHistory.user))
            .where(TicketHistory.ticket_id == ticket_id)
            .order_by(TicketHistory.created_at.asc(), TicketHistory.id.asc())
        )
        return list(self.db.scalars(statement))
