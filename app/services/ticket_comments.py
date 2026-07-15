import uuid
from http import HTTPStatus

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.core.exceptions import AppException
from app.models import TicketComment, TicketStatus
from app.repositories.ticket_comments import TicketCommentRepository
from app.schemas.ticket_comments import TicketCommentCreateRequest
from app.services.tickets import TicketService


class TicketCommentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = TicketCommentRepository(db)
        self.tickets = TicketService(db)

    def create_comment(
        self,
        *,
        context: AuthContext,
        ticket_id: uuid.UUID,
        payload: TicketCommentCreateRequest,
    ) -> TicketComment:
        ticket = self.tickets.get_ticket(context=context, ticket_id=ticket_id)
        if ticket.status == TicketStatus.CANCELLED:
            raise AppException(
                "Solicitacao cancelada nao aceita comentarios.",
                status_code=HTTPStatus.CONFLICT,
                code="cancelled_ticket_comment",
            )
        try:
            comment = self.repository.create_comment(
                ticket=ticket, author=context.user, content=payload.content
            )
            self.db.commit()
            return comment
        except (IntegrityError, SQLAlchemyError) as exc:
            self.db.rollback()
            raise comment_persistence_error() from exc

    def list_comments(
        self, *, context: AuthContext, ticket_id: uuid.UUID
    ) -> list[TicketComment]:
        ticket = self.tickets.get_ticket(context=context, ticket_id=ticket_id)
        return self.repository.list_comments(ticket_id=ticket.id)


def comment_persistence_error() -> AppException:
    return AppException(
        "Nao foi possivel salvar o comentario.",
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="comment_persistence_error",
    )
