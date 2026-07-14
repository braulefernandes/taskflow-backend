import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Organization


class CategoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_categories(
        self,
        *,
        organization_id: uuid.UUID,
        include_inactive: bool,
    ) -> list[Category]:
        statement = (
            select(Category)
            .where(Category.organization_id == organization_id)
            .order_by(Category.name.asc(), Category.id.asc())
        )
        if not include_inactive:
            statement = statement.where(Category.is_active.is_(True))
        return list(self.db.scalars(statement))

    def get_category(
        self,
        *,
        category_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Category | None:
        return self.db.scalar(
            select(Category)
            .where(Category.id == category_id)
            .where(Category.organization_id == organization_id)
        )

    def normalized_name_exists(
        self,
        *,
        organization_id: uuid.UUID,
        normalized_name: str,
        exclude_category_id: uuid.UUID | None = None,
    ) -> bool:
        statement = (
            select(Category.id)
            .where(Category.organization_id == organization_id)
            .where(Category.normalized_name == normalized_name)
        )
        if exclude_category_id is not None:
            statement = statement.where(Category.id != exclude_category_id)
        return self.db.scalar(statement) is not None

    def create_category(
        self,
        *,
        organization: Organization,
        name: str,
        normalized_name: str,
        description: str | None,
    ) -> Category:
        category = Category(
            organization=organization,
            name=name,
            normalized_name=normalized_name,
            description=description,
            is_active=True,
        )
        self.db.add(category)
        self.db.flush()
        return category
