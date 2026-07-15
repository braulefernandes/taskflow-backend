import uuid
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Ticket, TicketPriority, TicketStatus


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self, *, organization_id: uuid.UUID, now: datetime) -> object:
        resolution_seconds = self._resolution_seconds_expression()
        statement = select(
            func.count(Ticket.id).label("total"),
            *(
                func.sum(case((Ticket.status == status, 1), else_=0)).label(label)
                for status, label in (
                    (TicketStatus.PENDING, "pending"),
                    (TicketStatus.IN_PROGRESS, "in_progress"),
                    (TicketStatus.WAITING, "waiting"),
                    (TicketStatus.COMPLETED, "completed"),
                    (TicketStatus.CANCELLED, "cancelled"),
                )
            ),
            func.sum(
                case(
                    (
                        self.overdue_expression(now),
                        1,
                    ),
                    else_=0,
                )
            ).label("overdue"),
            func.avg(
                case(
                    (
                        (Ticket.status == TicketStatus.COMPLETED)
                        & Ticket.completed_at.is_not(None),
                        resolution_seconds,
                    )
                )
            ).label("average_resolution_seconds"),
        ).where(Ticket.organization_id == organization_id)
        return self.db.execute(statement).one()

    def status_distribution(
        self, *, organization_id: uuid.UUID
    ) -> dict[TicketStatus, int]:
        rows = self.db.execute(
            select(Ticket.status, func.count(Ticket.id))
            .where(Ticket.organization_id == organization_id)
            .group_by(Ticket.status)
        )
        return {status: int(count) for status, count in rows}

    def priority_distribution(
        self, *, organization_id: uuid.UUID
    ) -> dict[TicketPriority, int]:
        rows = self.db.execute(
            select(Ticket.priority, func.count(Ticket.id))
            .where(Ticket.organization_id == organization_id)
            .group_by(Ticket.priority)
        )
        return {priority: int(count) for priority, count in rows}

    def recent(self, *, organization_id: uuid.UUID, limit: int) -> list[Ticket]:
        statement = (
            select(Ticket)
            .options(joinedload(Ticket.category), joinedload(Ticket.assignee))
            .where(Ticket.organization_id == organization_id)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement))

    def overdue(
        self, *, organization_id: uuid.UUID, now: datetime, limit: int
    ) -> list[tuple[Ticket, int]]:
        overdue_seconds = self._overdue_seconds_expression(now)
        statement = (
            select(Ticket, overdue_seconds.label("overdue_seconds"))
            .options(joinedload(Ticket.category), joinedload(Ticket.assignee))
            .where(
                Ticket.organization_id == organization_id,
                self.overdue_expression(now),
            )
            .order_by(overdue_seconds.desc(), Ticket.id.desc())
            .limit(limit)
        )
        return [
            (ticket, int(seconds)) for ticket, seconds in self.db.execute(statement)
        ]

    @staticmethod
    def overdue_expression(now: datetime) -> object:
        return (
            Ticket.due_date.is_not(None)
            & (Ticket.due_date < now)
            & Ticket.status.not_in((TicketStatus.COMPLETED, TicketStatus.CANCELLED))
        )

    def _resolution_seconds_expression(self) -> object:
        if self.db.get_bind().dialect.name == "sqlite":
            return (
                func.julianday(Ticket.completed_at) - func.julianday(Ticket.created_at)
            ) * 86400.0
        return func.extract("epoch", Ticket.completed_at - Ticket.created_at)

    def _overdue_seconds_expression(self, now: datetime) -> object:
        if self.db.get_bind().dialect.name == "sqlite":
            return (func.julianday(now) - func.julianday(Ticket.due_date)) * 86400.0
        return func.extract("epoch", now - Ticket.due_date)
