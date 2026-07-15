import uuid
from http import HTTPStatus

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.core.authorization import ensure_role
from app.core.exceptions import AppException
from app.models import Category, OrganizationRole
from app.repositories.categories import CategoryRepository
from app.schemas.categories import (
    CategoryCreateRequest,
    CategoryStatusUpdateRequest,
    CategoryUpdateRequest,
)


class CategoryService:
    def __init__(
        self, db: Session, repository: CategoryRepository | None = None
    ) -> None:
        self.db = db
        self.repository = repository or CategoryRepository(db)

    def list_categories(
        self,
        *,
        context: AuthContext,
        include_inactive: bool,
    ) -> list[Category]:
        if include_inactive:
            ensure_role(context.membership, [OrganizationRole.ADMIN])
        return self.repository.list_categories(
            organization_id=context.organization.id,
            include_inactive=include_inactive,
        )

    def get_category(
        self,
        *,
        context: AuthContext,
        category_id: uuid.UUID,
    ) -> Category:
        category = self.repository.get_category(
            category_id=category_id,
            organization_id=context.organization.id,
        )
        if category is None:
            raise category_not_found_error()
        if not category.is_active and context.membership.role != OrganizationRole.ADMIN:
            raise category_not_found_error()
        return category

    def create_category(
        self,
        *,
        context: AuthContext,
        payload: CategoryCreateRequest,
    ) -> Category:
        normalized_name = payload.name.casefold()
        self._ensure_unique_name(
            organization_id=context.organization.id,
            normalized_name=normalized_name,
        )
        try:
            category = self.repository.create_category(
                organization=context.organization,
                name=payload.name,
                normalized_name=normalized_name,
                description=payload.description,
            )
            self.db.commit()
            self.db.refresh(category)
            return category
        except IntegrityError as exc:
            self.db.rollback()
            raise duplicate_category_error() from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise category_persistence_error() from exc

    def update_category(
        self,
        *,
        context: AuthContext,
        category_id: uuid.UUID,
        payload: CategoryUpdateRequest,
    ) -> Category:
        category = self.get_category(context=context, category_id=category_id)
        if "name" in payload.model_fields_set:
            assert payload.name is not None
            normalized_name = payload.name.casefold()
            self._ensure_unique_name(
                organization_id=context.organization.id,
                normalized_name=normalized_name,
                exclude_category_id=category.id,
            )
            category.name = payload.name
            category.normalized_name = normalized_name
        if "description" in payload.model_fields_set:
            category.description = payload.description
        return self._commit_update(category)

    def update_status(
        self,
        *,
        context: AuthContext,
        category_id: uuid.UUID,
        payload: CategoryStatusUpdateRequest,
    ) -> Category:
        category = self.get_category(context=context, category_id=category_id)
        category.is_active = payload.is_active
        return self._commit_update(category)

    def _ensure_unique_name(
        self,
        *,
        organization_id: uuid.UUID,
        normalized_name: str,
        exclude_category_id: uuid.UUID | None = None,
    ) -> None:
        if self.repository.normalized_name_exists(
            organization_id=organization_id,
            normalized_name=normalized_name,
            exclude_category_id=exclude_category_id,
        ):
            raise duplicate_category_error()

    def _commit_update(self, category: Category) -> Category:
        try:
            self.db.commit()
            self.db.refresh(category)
            return category
        except IntegrityError as exc:
            self.db.rollback()
            raise duplicate_category_error() from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise category_persistence_error() from exc


def duplicate_category_error() -> AppException:
    return AppException(
        "Ja existe uma categoria com este nome na organizacao.",
        status_code=HTTPStatus.CONFLICT,
        code="category_already_exists",
    )


def category_not_found_error() -> AppException:
    return AppException(
        "Recurso nao encontrado.",
        status_code=HTTPStatus.NOT_FOUND,
        code="resource_not_found",
    )


def category_persistence_error() -> AppException:
    return AppException(
        "Nao foi possivel salvar a categoria.",
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="category_persistence_error",
    )
