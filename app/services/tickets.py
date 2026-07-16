import uuid
from datetime import UTC, datetime
from http import HTTPStatus

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.core.exceptions import AppException
from app.models import (
    Category,
    OrganizationRole,
    Ticket,
    TicketHistoryAction,
    TicketStatus,
    User,
)
from app.repositories.categories import CategoryRepository
from app.repositories.ticket_history import TicketHistoryRepository
from app.repositories.tickets import TicketListCriteria, TicketRepository
from app.schemas.tickets import (
    TicketAssigneeUpdateRequest,
    TicketCreateRequest,
    TicketListFilters,
    TicketStatusUpdateRequest,
    TicketUpdateRequest,
    normalize_filter_datetime,
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
        self.history = TicketHistoryRepository(db)

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
            self.history.add_event(
                ticket=ticket,
                user=context.user,
                action=TicketHistoryAction.CREATED,
                new_value=safe_history_value(ticket.title),
            )
            self.db.commit()
            return self.get_ticket(context=context, ticket_id=ticket.id)
        except (IntegrityError, SQLAlchemyError) as exc:
            self.db.rollback()
            raise persistence_error() from exc

    def list_tickets(
        self, *, context: AuthContext, filters: TicketListFilters
    ) -> tuple[list[Ticket], int]:
        criteria = TicketListCriteria(
            search=filters.search,
            status=filters.status,
            priority=filters.priority,
            category_id=filters.category_id,
            assignee_id=filters.assignee_id,
            created_from=normalize_filter_datetime(filters.created_from),
            created_to=normalize_filter_datetime(filters.created_to),
            due_from=normalize_filter_datetime(filters.due_from),
            due_to=normalize_filter_datetime(filters.due_to),
            overdue=filters.overdue,
            sort_by=filters.sort_by.value,
            sort_order=filters.sort_order.value,
            now=utc_now(),
        )
        return self.repository.list_tickets(
            organization_id=context.organization.id,
            user_id=context.user.id,
            role=context.membership.role,
            criteria=criteria,
            offset=(filters.page - 1) * filters.page_size,
            limit=filters.page_size,
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
                "Solicitação cancelada não pode ser editada.",
                status_code=HTTPStatus.CONFLICT,
                code="cancelled_ticket_edit",
            )
        self._ensure_can_edit(context=context, ticket=ticket)
        if payload.model_fields_set & {"priority", "due_date"}:
            self._ensure_can_change_planning(context=context, ticket=ticket)
        new_category = None
        if "category_id" in payload.model_fields_set:
            assert payload.category_id is not None
            new_category = self._get_active_category(
                context=context, category_id=payload.category_id
            )
        if "due_date" in payload.model_fields_set:
            self._validate_due_date(payload.due_date)
        try:
            for field in payload.model_fields_set:
                old_value = getattr(ticket, field)
                new_value = getattr(payload, field)
                if old_value == new_value:
                    continue
                if field == "category_id":
                    assert new_category is not None
                    old_history_value = entity_history_value(
                        ticket.category_id, ticket.category.name
                    )
                    new_history_value = entity_history_value(
                        new_category.id, new_category.name
                    )
                else:
                    old_history_value = history_field_value(field, old_value)
                    new_history_value = history_field_value(field, new_value)
                setattr(ticket, field, new_value)
                self.history.add_event(
                    ticket=ticket,
                    user=context.user,
                    action=history_action_for_field(field),
                    field_name=field,
                    old_value=old_history_value,
                    new_value=new_history_value,
                )
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
                "Solicitação concluída não pode ser cancelada.",
                status_code=HTTPStatus.CONFLICT,
                code="completed_ticket_cancellation",
            )

        previous_status = ticket.status
        ticket.status = TicketStatus.CANCELLED
        ticket.cancelled_at = utc_now()
        ticket.completed_at = None
        try:
            self.history.add_event(
                ticket=ticket,
                user=context.user,
                action=TicketHistoryAction.CANCELLED,
                field_name="status",
                old_value=previous_status.value,
                new_value=TicketStatus.CANCELLED.value,
            )
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
                "Transição de status inválida.",
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
                "A solicitação deve possuir responsável para este status.",
                status_code=HTTPStatus.CONFLICT,
                code="assignee_required_for_status",
            )

        previous_status = ticket.status
        now = utc_now()
        if payload.status == TicketStatus.IN_PROGRESS:
            if ticket.started_at is None:
                ticket.started_at = now
            if ticket.status == TicketStatus.COMPLETED:
                ticket.completed_at = None
        elif payload.status == TicketStatus.COMPLETED:
            ticket.completed_at = now

        ticket.status = payload.status
        try:
            action = TicketHistoryAction.STATUS_CHANGED
            if payload.status == TicketStatus.COMPLETED:
                action = TicketHistoryAction.COMPLETED
            elif previous_status == TicketStatus.COMPLETED:
                action = TicketHistoryAction.REOPENED
            self.history.add_event(
                ticket=ticket,
                user=context.user,
                action=action,
                field_name="status",
                old_value=previous_status.value,
                new_value=payload.status.value,
            )
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
                    "Membership do responsável está inativo.",
                    "assignee_membership_inactive",
                )
            if not membership.user.is_active:
                raise assignment_error(
                    "Usuário responsável está inativo.",
                    "assignee_user_inactive",
                )
            if membership.role not in {
                OrganizationRole.ADMIN,
                OrganizationRole.MANAGER,
                OrganizationRole.AGENT,
            }:
                raise assignment_error(
                    "Papel não permitido para responsável.",
                    "assignee_role_not_allowed",
                )
            assignee = membership.user

        if ticket.assignee_id == payload.assignee_id:
            return ticket

        previous_assignee = ticket.assignee
        ticket.assignee = assignee
        try:
            action = TicketHistoryAction.ASSIGNED
            if assignee is None:
                action = TicketHistoryAction.ASSIGNEE_REMOVED
            elif previous_assignee is not None:
                action = TicketHistoryAction.ASSIGNEE_CHANGED
            self.history.add_event(
                ticket=ticket,
                user=context.user,
                action=action,
                field_name="assignee_id",
                old_value=user_history_value(previous_assignee),
                new_value=user_history_value(assignee),
            )
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
        if comparable <= utc_now():
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
                "Prioridade e prazo não podem ser alterados em estado terminal.",
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
                "Solicitação cancelada não pode ter o responsável alterado.",
                status_code=HTTPStatus.CONFLICT,
                code="cancelled_ticket_assignment",
            )
        if ticket.status == TicketStatus.COMPLETED:
            raise AppException(
                "Solicitação concluída deve ser reaberta antes de alterar o responsável.",
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
        "Recurso não encontrado.",
        status_code=HTTPStatus.NOT_FOUND,
        code="resource_not_found",
    )


def persistence_error() -> AppException:
    return AppException(
        "Não foi possível salvar a solicitação.",
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="ticket_persistence_error",
    )


def assignment_error(message: str, code: str) -> AppException:
    return AppException(message, status_code=HTTPStatus.BAD_REQUEST, code=code)


def utc_now() -> datetime:
    return datetime.now(UTC)


HISTORY_ACTION_BY_FIELD = {
    "title": TicketHistoryAction.TITLE_CHANGED,
    "description": TicketHistoryAction.DESCRIPTION_CHANGED,
    "category_id": TicketHistoryAction.CATEGORY_CHANGED,
    "priority": TicketHistoryAction.PRIORITY_CHANGED,
    "due_date": TicketHistoryAction.DUE_DATE_CHANGED,
}
SENSITIVE_HISTORY_TERMS = ("password", "senha", "hash", "token", "secret", "segredo")


def history_action_for_field(field: str) -> TicketHistoryAction:
    return HISTORY_ACTION_BY_FIELD[field]


def history_field_value(field: str, value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat()
    if hasattr(value, "value"):
        return str(value.value)
    return safe_history_value(str(value))


def safe_history_value(value: str) -> str:
    if any(term in value.casefold() for term in SENSITIVE_HISTORY_TERMS):
        return "[REDACTED]"
    if len(value) > 2000:
        return f"{value[:1999]}…"
    return value


def entity_history_value(entity_id: uuid.UUID, name: str) -> str:
    return f"{entity_id} | {safe_history_value(name)}"


def user_history_value(user: User | None) -> str | None:
    if user is None:
        return None
    return entity_history_value(user.id, user.name)
