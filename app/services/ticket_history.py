import uuid

from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.models import TicketHistory
from app.repositories.ticket_history import TicketHistoryRepository
from app.services.tickets import TicketService


class TicketHistoryService:
    def __init__(self, db: Session) -> None:
        self.repository = TicketHistoryRepository(db)
        self.tickets = TicketService(db)

    def list_history(
        self, *, context: AuthContext, ticket_id: uuid.UUID
    ) -> list[TicketHistory]:
        ticket = self.tickets.get_ticket(context=context, ticket_id=ticket_id)
        return self.repository.list_events(ticket_id=ticket.id)
