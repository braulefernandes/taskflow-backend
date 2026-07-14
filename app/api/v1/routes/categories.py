import uuid
from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_admin, require_authenticated_user
from app.db.session import get_db
from app.schemas.categories import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryStatusUpdateRequest,
    CategoryUpdateRequest,
)
from app.services.categories import CategoryService

router = APIRouter(prefix="/categories")


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    include_inactive: bool = False,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> list[CategoryResponse]:
    return CategoryService(db).list_categories(
        context=context,
        include_inactive=include_inactive,
    )


@router.post("", response_model=CategoryResponse, status_code=HTTPStatus.CREATED)
def create_category(
    payload: CategoryCreateRequest,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CategoryResponse:
    return CategoryService(db).create_category(context=context, payload=payload)


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: uuid.UUID,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> CategoryResponse:
    return CategoryService(db).get_category(context=context, category_id=category_id)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdateRequest,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CategoryResponse:
    return CategoryService(db).update_category(
        context=context,
        category_id=category_id,
        payload=payload,
    )


@router.patch("/{category_id}/status", response_model=CategoryResponse)
def update_category_status(
    category_id: uuid.UUID,
    payload: CategoryStatusUpdateRequest,
    context: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CategoryResponse:
    return CategoryService(db).update_status(
        context=context,
        category_id=category_id,
        payload=payload,
    )
