import uuid
from http import HTTPStatus

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_admin
from app.db.session import get_db
from app.models import OrganizationMember, OrganizationRole
from app.schemas.members import (
    MemberCreateRequest,
    MemberListResponse,
    MemberResponse,
    MemberRoleUpdateRequest,
    MemberStatusUpdateRequest,
)
from app.services.members import MemberService

router = APIRouter(prefix="/members")


def member_response(membership: OrganizationMember) -> MemberResponse:
    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        name=membership.user.name,
        email=membership.user.email,
        role=membership.role,
        is_active=membership.is_active,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@router.get("", response_model=MemberListResponse)
def list_members(
    search: str | None = Query(default=None, max_length=320),
    role: OrganizationRole | None = None,
    is_active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberListResponse:
    memberships, total = MemberService(db).list_members(
        context=context,
        search=search,
        role=role,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return MemberListResponse(
        items=[member_response(membership) for membership in memberships],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=MemberResponse, status_code=HTTPStatus.CREATED)
def create_member(
    payload: MemberCreateRequest,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberResponse:
    membership = MemberService(db).create_member(context=context, payload=payload)
    return member_response(membership)


@router.get("/{membership_id}", response_model=MemberResponse)
def get_member(
    membership_id: uuid.UUID,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberResponse:
    membership = MemberService(db).get_member(
        context=context,
        membership_id=membership_id,
    )
    return member_response(membership)


@router.patch("/{membership_id}", response_model=MemberResponse)
def update_member_role(
    membership_id: uuid.UUID,
    payload: MemberRoleUpdateRequest,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberResponse:
    membership = MemberService(db).update_role(
        context=context,
        membership_id=membership_id,
        payload=payload,
    )
    return member_response(membership)


@router.patch("/{membership_id}/status", response_model=MemberResponse)
def update_member_status(
    membership_id: uuid.UUID,
    payload: MemberStatusUpdateRequest,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberResponse:
    membership = MemberService(db).update_status(
        context=context,
        membership_id=membership_id,
        payload=payload,
    )
    return member_response(membership)
