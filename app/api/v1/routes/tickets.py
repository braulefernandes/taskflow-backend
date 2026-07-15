import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    AuthContext,
    require_admin_or_manager,
    require_authenticated_user,
)
from app.db.session import get_db
from app.schemas.tickets import (
    TicketCreateRequest,
    TicketAssigneeUpdateRequest,
    TicketListFilters,
    TicketListResponse,
    TicketResponse,
    TicketStatusUpdateRequest,
    TicketUpdateRequest,
)
from app.schemas.ticket_comments import (
    TicketCommentCreateRequest,
    TicketCommentResponse,
)
from app.schemas.ticket_history import TicketHistoryResponse
from app.services.ticket_comments import TicketCommentService
from app.services.ticket_history import TicketHistoryService
from app.services.tickets import TicketService

router = APIRouter(prefix="/tickets")


@router.post("", response_model=TicketResponse, status_code=HTTPStatus.CREATED)
def create_ticket(
    payload: TicketCreateRequest,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    return TicketService(db).create_ticket(context=context, payload=payload)


@router.get("", response_model=TicketListResponse)
def list_tickets(
    filters: Annotated[TicketListFilters, Query()],
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TicketListResponse:
    items, total = TicketService(db).list_tickets(context=context, filters=filters)
    return TicketListResponse.build(filters=filters, total=total, items=items)


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: uuid.UUID,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    return TicketService(db).get_ticket(context=context, ticket_id=ticket_id)


@router.patch("/{ticket_id}", response_model=TicketResponse)
def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdateRequest,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    return TicketService(db).update_ticket(
        context=context, ticket_id=ticket_id, payload=payload
    )


@router.patch("/{ticket_id}/assignee", response_model=TicketResponse)
def update_ticket_assignee(
    ticket_id: uuid.UUID,
    payload: TicketAssigneeUpdateRequest,
    context: AuthContext = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> TicketResponse:
    return TicketService(db).update_assignee(
        context=context, ticket_id=ticket_id, payload=payload
    )


@router.patch("/{ticket_id}/status", response_model=TicketResponse)
def update_ticket_status(
    ticket_id: uuid.UUID,
    payload: TicketStatusUpdateRequest,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    return TicketService(db).update_status(
        context=context, ticket_id=ticket_id, payload=payload
    )


@router.post("/{ticket_id}/cancel", response_model=TicketResponse)
def cancel_ticket(
    ticket_id: uuid.UUID,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TicketResponse:
    return TicketService(db).cancel_ticket(context=context, ticket_id=ticket_id)


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentResponse,
    status_code=HTTPStatus.CREATED,
)
def create_ticket_comment(
    ticket_id: uuid.UUID,
    payload: TicketCommentCreateRequest,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TicketCommentResponse:
    return TicketCommentService(db).create_comment(
        context=context, ticket_id=ticket_id, payload=payload
    )


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentResponse])
def list_ticket_comments(
    ticket_id: uuid.UUID,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> list[TicketCommentResponse]:
    return TicketCommentService(db).list_comments(context=context, ticket_id=ticket_id)


@router.get("/{ticket_id}/history", response_model=list[TicketHistoryResponse])
def list_ticket_history(
    ticket_id: uuid.UUID,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> list[TicketHistoryResponse]:
    return TicketHistoryService(db).list_history(context=context, ticket_id=ticket_id)
