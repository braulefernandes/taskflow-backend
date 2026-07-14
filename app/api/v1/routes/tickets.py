import uuid
from http import HTTPStatus

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
    TicketListResponse,
    TicketResponse,
    TicketUpdateRequest,
)
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TicketListResponse:
    items, total = TicketService(db).list_tickets(
        context=context, page=page, page_size=page_size
    )
    return TicketListResponse(page=page, page_size=page_size, total=total, items=items)


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
