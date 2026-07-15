import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Organization,
    OrganizationMember,
    OrganizationRole,
    Ticket,
    TicketPriority,
    TicketStatus,
    User,
)


@dataclass(frozen=True)
class TicketListCriteria:
    search: str | None
    status: TicketStatus | None
    priority: TicketPriority | None
    category_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    created_from: datetime | None
    created_to: datetime | None
    due_from: datetime | None
    due_to: datetime | None
    overdue: bool | None
    sort_by: str
    sort_order: str
    now: datetime


class TicketRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def visibility_filters(
        *, organization_id: uuid.UUID, user_id: uuid.UUID, role: OrganizationRole
    ) -> list[object]:
        filters: list[object] = [Ticket.organization_id == organization_id]
        if role == OrganizationRole.REQUESTER:
            filters.append(Ticket.requester_id == user_id)
        elif role == OrganizationRole.AGENT:
            filters.append(
                or_(Ticket.requester_id == user_id, Ticket.assignee_id == user_id)
            )
        return filters

    def list_tickets(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: OrganizationRole,
        criteria: TicketListCriteria,
        offset: int,
        limit: int,
    ) -> tuple[list[Ticket], int]:
        filters = self.visibility_filters(
            organization_id=organization_id, user_id=user_id, role=role
        )
        filters.extend(self.list_filters(criteria))
        total = self.db.scalar(select(func.count()).select_from(Ticket).where(*filters))
        sort_column = (
            Ticket.due_date if criteria.sort_by == "due_date" else Ticket.created_at
        )
        direction = (
            sort_column.asc if criteria.sort_order == "asc" else sort_column.desc
        )
        id_direction = Ticket.id.asc if criteria.sort_order == "asc" else Ticket.id.desc
        statement = (
            select(Ticket)
            .options(*self._response_loads())
            .where(*filters)
            .order_by(direction().nulls_last(), id_direction())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(statement)), int(total or 0)

    @staticmethod
    def list_filters(criteria: TicketListCriteria) -> list[object]:
        filters: list[object] = []
        if criteria.search is not None:
            escaped = (
                criteria.search.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            filters.append(Ticket.title.ilike(f"%{escaped}%", escape="\\"))
        if criteria.status is not None:
            filters.append(Ticket.status == criteria.status)
        if criteria.priority is not None:
            filters.append(Ticket.priority == criteria.priority)
        if criteria.category_id is not None:
            filters.append(Ticket.category_id == criteria.category_id)
        if criteria.assignee_id is not None:
            filters.append(Ticket.assignee_id == criteria.assignee_id)
        if criteria.created_from is not None:
            filters.append(Ticket.created_at >= criteria.created_from)
        if criteria.created_to is not None:
            filters.append(Ticket.created_at <= criteria.created_to)
        if criteria.due_from is not None:
            filters.append(Ticket.due_date >= criteria.due_from)
        if criteria.due_to is not None:
            filters.append(Ticket.due_date <= criteria.due_to)
        overdue_expression = and_(
            Ticket.due_date.is_not(None),
            Ticket.due_date < criteria.now,
            Ticket.status.not_in((TicketStatus.COMPLETED, TicketStatus.CANCELLED)),
        )
        if criteria.overdue is True:
            filters.append(overdue_expression)
        elif criteria.overdue is False:
            filters.append(not_(overdue_expression))
        return filters

    def get_visible_ticket(
        self,
        *,
        ticket_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: OrganizationRole,
    ) -> Ticket | None:
        filters = self.visibility_filters(
            organization_id=organization_id, user_id=user_id, role=role
        )
        return self.db.scalar(
            select(Ticket)
            .options(*self._response_loads())
            .where(Ticket.id == ticket_id, *filters)
        )

    def create_ticket(
        self,
        *,
        organization: Organization,
        requester: User,
        title: str,
        description: str,
        category_id: uuid.UUID,
        priority: object,
        due_date: object,
    ) -> Ticket:
        ticket = Ticket(
            organization=organization,
            requester=requester,
            title=title,
            description=description,
            category_id=category_id,
            priority=priority,
            due_date=due_date,
        )
        self.db.add(ticket)
        self.db.flush()
        return ticket

    def get_assignment_membership(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMember | None:
        return self.db.scalar(
            select(OrganizationMember)
            .options(joinedload(OrganizationMember.user))
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )

    @staticmethod
    def _response_loads() -> tuple[object, ...]:
        return (
            joinedload(Ticket.organization),
            joinedload(Ticket.category),
            joinedload(Ticket.requester),
            joinedload(Ticket.assignee),
        )
