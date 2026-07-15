import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Organization, OrganizationMember, OrganizationRole, Ticket, User


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
        offset: int,
        limit: int,
    ) -> tuple[list[Ticket], int]:
        filters = self.visibility_filters(
            organization_id=organization_id, user_id=user_id, role=role
        )
        total = self.db.scalar(select(func.count()).select_from(Ticket).where(*filters))
        statement = (
            select(Ticket)
            .options(*self._response_loads())
            .where(*filters)
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(statement)), int(total or 0)

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
