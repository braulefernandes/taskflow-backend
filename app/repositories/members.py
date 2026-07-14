import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Organization, OrganizationMember, OrganizationRole, User


class MemberRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_members(
        self,
        *,
        organization_id: uuid.UUID,
        search: str | None,
        role: OrganizationRole | None,
        is_active: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[OrganizationMember], int]:
        filters = [OrganizationMember.organization_id == organization_id]
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(User.name.ilike(term), User.email.ilike(term)))
        if role is not None:
            filters.append(OrganizationMember.role == role)
        if is_active is not None:
            filters.append(OrganizationMember.is_active.is_(is_active))

        total = self.db.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .join(OrganizationMember.user)
            .where(*filters)
        )
        statement = (
            select(OrganizationMember)
            .join(OrganizationMember.user)
            .options(joinedload(OrganizationMember.user))
            .where(*filters)
            .order_by(OrganizationMember.created_at.asc(), OrganizationMember.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(statement)), int(total or 0)

    def get_member(
        self,
        *,
        membership_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> OrganizationMember | None:
        return self.db.scalar(
            select(OrganizationMember)
            .options(joinedload(OrganizationMember.user))
            .where(OrganizationMember.id == membership_id)
            .where(OrganizationMember.organization_id == organization_id)
        )

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def membership_exists(
        self,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> bool:
        return self.db.scalar(
            select(OrganizationMember.id)
            .where(OrganizationMember.user_id == user_id)
            .where(OrganizationMember.organization_id == organization_id)
        ) is not None

    def create_user(self, *, name: str, email: str, password_hash: str) -> User:
        user = User(name=name, email=email, password_hash=password_hash, is_active=True)
        self.db.add(user)
        self.db.flush()
        return user

    def create_membership(
        self,
        *,
        user: User,
        organization: Organization,
        role: OrganizationRole,
    ) -> OrganizationMember:
        membership = OrganizationMember(
            user=user,
            organization=organization,
            role=role,
            is_active=True,
        )
        self.db.add(membership)
        self.db.flush()
        return membership

    def count_active_admins_for_update(self, organization_id: uuid.UUID) -> int:
        statement = (
            select(OrganizationMember.id)
            .where(OrganizationMember.organization_id == organization_id)
            .where(OrganizationMember.role == OrganizationRole.ADMIN)
            .where(OrganizationMember.is_active.is_(True))
            .with_for_update()
        )
        return len(list(self.db.scalars(statement)))
