import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import TicketPriority, TicketStatus
from app.repositories.dashboard import DashboardRepository
from app.schemas.dashboard import (
    DashboardSummaryResponse,
    OverdueTicketResponse,
    PriorityDistributionItem,
    RecentTicketResponse,
    StatusDistributionItem,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.repository = DashboardRepository(db)

    def summary(self, *, organization_id: uuid.UUID) -> DashboardSummaryResponse:
        row = self.repository.summary(organization_id=organization_id, now=utc_now())
        average_seconds = row.average_resolution_seconds
        return DashboardSummaryResponse(
            total=int(row.total or 0),
            pending=int(row.pending or 0),
            in_progress=int(row.in_progress or 0),
            waiting=int(row.waiting or 0),
            completed=int(row.completed or 0),
            cancelled=int(row.cancelled or 0),
            overdue=int(row.overdue or 0),
            average_resolution_hours=(
                round(float(average_seconds) / 3600, 2)
                if average_seconds is not None
                else None
            ),
        )

    def status_distribution(
        self, *, organization_id: uuid.UUID
    ) -> list[StatusDistributionItem]:
        counts = self.repository.status_distribution(organization_id=organization_id)
        return [
            StatusDistributionItem(status=status, count=counts.get(status, 0))
            for status in TicketStatus
        ]

    def priority_distribution(
        self, *, organization_id: uuid.UUID
    ) -> list[PriorityDistributionItem]:
        counts = self.repository.priority_distribution(organization_id=organization_id)
        return [
            PriorityDistributionItem(priority=priority, count=counts.get(priority, 0))
            for priority in TicketPriority
        ]

    def recent(
        self, *, organization_id: uuid.UUID, limit: int
    ) -> list[RecentTicketResponse]:
        return [
            RecentTicketResponse.model_validate(ticket, from_attributes=True)
            for ticket in self.repository.recent(
                organization_id=organization_id, limit=limit
            )
        ]

    def overdue(
        self, *, organization_id: uuid.UUID, limit: int
    ) -> list[OverdueTicketResponse]:
        return [
            OverdueTicketResponse.model_validate(
                {
                    "id": ticket.id,
                    "title": ticket.title,
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "due_date": ticket.due_date,
                    "created_at": ticket.created_at,
                    "category": ticket.category,
                    "assignee": ticket.assignee,
                    "overdue_seconds": seconds,
                }
            )
            for ticket, seconds in self.repository.overdue(
                organization_id=organization_id,
                now=utc_now(),
                limit=limit,
            )
        ]
