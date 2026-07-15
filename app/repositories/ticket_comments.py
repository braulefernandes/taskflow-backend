import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Ticket, TicketComment, User


class TicketCommentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_comment(
        self, *, ticket: Ticket, author: User, content: str
    ) -> TicketComment:
        comment = TicketComment(ticket=ticket, author=author, content=content)
        self.db.add(comment)
        self.db.flush()
        self.db.refresh(comment)
        return comment

    def list_comments(self, *, ticket_id: uuid.UUID) -> list[TicketComment]:
        statement = (
            select(TicketComment)
            .options(joinedload(TicketComment.author))
            .where(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at.asc(), TicketComment.id.asc())
        )
        return list(self.db.scalars(statement))
