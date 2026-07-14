import uuid
from datetime import UTC, datetime
from http import HTTPStatus

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.core.exceptions import AppException
from app.models import Category, OrganizationRole, Ticket, TicketStatus
from app.repositories.categories import CategoryRepository
from app.repositories.tickets import TicketRepository
from app.schemas.tickets import (
    TicketAssigneeUpdateRequest,
    TicketCreateRequest,
    TicketStatusUpdateRequest,
    TicketUpdateRequest,
)


class TicketService:
    STATUS_TRANSITIONS = {
        TicketStatus.PENDING: {TicketStatus.IN_PROGRESS, TicketStatus.WAITING},
        TicketStatus.IN_PROGRESS: {TicketStatus.WAITING, TicketStatus.COMPLETED},
        TicketStatus.WAITING: {TicketStatus.IN_PROGRESS, TicketStatus.COMPLETED},
        TicketStatus.COMPLETED: {TicketStatus.IN_PROGRESS},
        TicketStatus.CANCELLED: set(),
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = TicketRepository(db)
        self.categories = CategoryRepository(db)

    def create_ticket(
        self, *, context: AuthContext, payload: TicketCreateRequest
    ) -> Ticket:
        self._validate_due_date(payload.due_date)
        self._get_active_category(context=context, category_id=payload.category_id)
        try:
            ticket = self.repository.create_ticket(
                organization=context.organization,
                requester=context.user,
                title=payload.title,
                description=payload.description,
                category_id=payload.category_id,
                priority=payload.priority,
                due_date=payload.due_date,
            )
            self.db.commit()
            return self.get_ticket(context=context, ticket_id=ticket.id)
        except (IntegrityError, SQLAlchemyError) as exc:
            self.db.rollback()
            raise persistence_error() from exc

    def list_tickets(
        self, *, context: AuthContext, page: int, page_size: int
    ) -> tuple[list[Ticket], int]:
        return self.repository.list_tickets(
            organization_id=context.organization.id,
            user_id=context.user.id,
            role=context.membership.role,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    def get_ticket(self, *, context: AuthContext, ticket_id: uuid.UUID) -> Ticket:
        ticket = self.repository.get_visible_ticket(
            ticket_id=ticket_id,
            organization_id=context.organization.id,
            user_id=context.user.id,
            role=context.membership.role,
        )
        if ticket is None:
            raise not_found_error()
        return ticket

    def update_ticket(
        self,
        *,
        context: AuthContext,
        ticket_id: uuid.UUID,
        payload: TicketUpdateRequest,
    ) -> Ticket:
        ticket = self.get_ticket(context=context, ticket_id=ticket_id)
        if ticket.status == TicketStatus.CANCELLED and not payload.model_fields_set & {
            "priority",
            "due_date",
        }:
            raise AppException(
                "Solicitacao cancelada nao pode ser editada.",
                status_code=HTTPStatus.CONFLICT,
                code="cancelled_ticket_edit",
            )
        self._ensure_can_edit(context=context, ticket=ticket)
        if payload.model_fields_set & {"priority", "due_date"}:
            self._ensure_can_change_planning(context=context, ticket=ticket)
        if "category_id" in payload.model_fields_set:
            assert payload.category_id is not None
            self._get_active_category(context=context, category_id=payload.category_id)
        if "due_date" in payload.model_fields_set:
            self._validate_due_date(payload.due_date)
        for field in payload.model_fields_set:
            setattr(ticket, field, getattr(payload, field))
        try:
            self.db.commit()
            return self.get_ticket(context=context, ticket_id=ticket.id)
        except (IntegrityError, SQLAlchemyError) as exc:
            self.db.rollback()
            raise persistence_error() from exc

    def cancel_ticket(self, *, context: AuthContext, ticket_id: uuid.UUID) -> Ticket:
        ticket = self.get_ticket(context=context, ticket_id=ticket_id)
        self._ensure_can_cancel(context=context, ticket=ticket)
        if ticket.status == TicketStatus.CANCELLED:
            return ticket
        if ticket.status == TicketStatus.COMPLETED:
            raise AppException(
                "Solicitacao concluida nao pode ser cancelada.",
                status_code=HTTPStatus.CONFLICT,
                code="completed_ticket_cancellation",
            )

        ticket.status = TicketStatus.CANCELLED
        ticket.cancelled_at = datetime.now(UTC)
        ticket.completed_at = None
        try:
            self.db.commit()
            return self.get_ticket(context=context, ticket_id=ticket.id)
        except (IntegrityError, SQLAlchemyError) as exc:
            self.db.rollback()
            raise persistence_error() from exc

    def update_status(
        self,
        *,
        context: AuthContext,
        ticket_id: uuid.UUID,
        payload: TicketStatusUpdateRequest,
    ) -> Ticket:
        ticket = self.get_ticket(context=context, ticket_id=ticket_id)
        self._ensure_can_change_status(context=context, ticket=ticket)
        if payload.status not in self.STATUS_TRANSITIONS[ticket.status]:
            raise AppException(
                "Transicao de status invalida.",
                status_code=HTTPStatus.CONFLICT,
                code="invalid_status_transition",
            )
        if (
            payload.status
            in {
                TicketStatus.IN_PROGRESS,
                TicketStatus.WAITING,
                TicketStatus.COMPLETED,
            }
            and ticket.assignee_id is None
        ):
            raise AppException(
                "A solicitacao deve possuir responsavel para este status.",
                status_code=HTTPStatus.CONFLICT,
                code="assignee_required_for_status",
            )

        now = datetime.now(UTC)
        if payload.status == TicketStatus.IN_PROGRESS:
            if ticket.started_at is None:
                ticket.started_at = now
            if ticket.status == TicketStatus.COMPLETED:
                ticket.completed_at = None
        elif payload.status == TicketStatus.COMPLETED:
            ticket.completed_at = now

        ticket.status = payload.status
        try:
            self.db.commit()
            return self.get_ticket(context=context, ticket_id=ticket.id)
        except (IntegrityError, SQLAlchemyError) as exc:
            self.db.rollback()
            raise persistence_error() from exc

    def update_assignee(
        self,
        *,
        context: AuthContext,
        ticket_id: uuid.UUID,
        payload: TicketAssigneeUpdateRequest,
    ) -> Ticket:
        ticket = self.get_ticket(context=context, ticket_id=ticket_id)
        self._ensure_assignment_allowed(ticket)

        assignee = None
        if payload.assignee_id is not None:
            membership = self.repository.get_assignment_membership(
                organization_id=context.organization.id,
                user_id=payload.assignee_id,
            )
            if membership is None:
                raise not_found_error()
            if not membership.is_active:
                raise assignment_error(
                    "Membership do responsavel esta inativo.",
                    "assignee_membership_inactive",
                )
            if not membership.user.is_active:
                raise assignment_error(
                    "Usuario responsavel esta inativo.",
                    "assignee_user_inactive",
                )
            if membership.role not in {
                OrganizationRole.ADMIN,
                OrganizationRole.MANAGER,
                OrganizationRole.AGENT,
            }:
                raise assignment_error(
                    "Papel nao permitido para responsavel.",
                    "assignee_role_not_allowed",
                )
            assignee = membership.user

        if ticket.assignee_id == payload.assignee_id:
            return ticket

        ticket.assignee = assignee
        try:
            self.db.commit()
            return self.get_ticket(context=context, ticket_id=ticket.id)
        except (IntegrityError, SQLAlchemyError) as exc:
            self.db.rollback()
            raise persistence_error() from exc

    def _get_active_category(
        self, *, context: AuthContext, category_id: uuid.UUID
    ) -> Category:
        category = self.categories.get_category(
            category_id=category_id, organization_id=context.organization.id
        )
        if category is None:
            raise not_found_error()
        if not category.is_active:
            raise AppException(
                "Categoria inativa.",
                status_code=HTTPStatus.BAD_REQUEST,
                code="category_inactive",
            )
        return category

    @staticmethod
    def _validate_due_date(due_date: datetime | None) -> None:
        if due_date is None:
            return
        comparable = (
            due_date if due_date.tzinfo is not None else due_date.replace(tzinfo=UTC)
        )
        if comparable <= datetime.now(UTC):
            raise AppException(
                "O prazo deve estar no futuro.",
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="due_date_in_past",
            )

    @staticmethod
    def _ensure_can_edit(*, context: AuthContext, ticket: Ticket) -> None:
        if context.membership.role in {
            OrganizationRole.ADMIN,
            OrganizationRole.MANAGER,
        }:
            return
        if (
            context.membership.role == OrganizationRole.REQUESTER
            and ticket.requester_id == context.user.id
            and ticket.status == TicketStatus.PENDING
            and ticket.assignee_id is None
        ):
            return
        raise AppException(
            "Papel insuficiente.",
            status_code=HTTPStatus.FORBIDDEN,
            code="insufficient_role",
        )

    @staticmethod
    def _ensure_can_change_planning(*, context: AuthContext, ticket: Ticket) -> None:
        if context.membership.role not in {
            OrganizationRole.ADMIN,
            OrganizationRole.MANAGER,
        }:
            raise AppException(
                "Papel insuficiente.",
                status_code=HTTPStatus.FORBIDDEN,
                code="insufficient_role",
            )
        if ticket.status in {TicketStatus.COMPLETED, TicketStatus.CANCELLED}:
            raise AppException(
                "Prioridade e prazo nao podem ser alterados em estado terminal.",
                status_code=HTTPStatus.CONFLICT,
                code="terminal_ticket_planning_update",
            )

    @staticmethod
    def _ensure_can_change_status(*, context: AuthContext, ticket: Ticket) -> None:
        if context.membership.role in {
            OrganizationRole.ADMIN,
            OrganizationRole.MANAGER,
        }:
            return
        if (
            context.membership.role == OrganizationRole.AGENT
            and ticket.assignee_id == context.user.id
        ):
            return
        raise AppException(
            "Papel insuficiente.",
            status_code=HTTPStatus.FORBIDDEN,
            code="insufficient_role",
        )

    @staticmethod
    def _ensure_assignment_allowed(ticket: Ticket) -> None:
        if ticket.status == TicketStatus.CANCELLED:
            raise AppException(
                "Solicitacao cancelada nao pode ter o responsavel alterado.",
                status_code=HTTPStatus.CONFLICT,
                code="cancelled_ticket_assignment",
            )
        if ticket.status == TicketStatus.COMPLETED:
            raise AppException(
                "Solicitacao concluida deve ser reaberta antes de alterar o responsavel.",
                status_code=HTTPStatus.CONFLICT,
                code="completed_ticket_assignment",
            )

    @staticmethod
    def _ensure_can_cancel(*, context: AuthContext, ticket: Ticket) -> None:
        if context.membership.role in {
            OrganizationRole.ADMIN,
            OrganizationRole.MANAGER,
        }:
            return
        if (
            context.membership.role == OrganizationRole.REQUESTER
            and ticket.requester_id == context.user.id
            and ticket.status in {TicketStatus.PENDING, TicketStatus.CANCELLED}
        ):
            return
        raise AppException(
            "Papel insuficiente.",
            status_code=HTTPStatus.FORBIDDEN,
            code="insufficient_role",
        )


def not_found_error() -> AppException:
    return AppException(
        "Recurso nao encontrado.",
        status_code=HTTPStatus.NOT_FOUND,
        code="resource_not_found",
    )


def persistence_error() -> AppException:
    return AppException(
        "Nao foi possivel salvar a solicitacao.",
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="ticket_persistence_error",
    )


def assignment_error(message: str, code: str) -> AppException:
    return AppException(message, status_code=HTTPStatus.BAD_REQUEST, code=code)
