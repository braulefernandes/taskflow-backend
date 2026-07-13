from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, OrganizationMember, OrganizationRole, User


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def organization_slug_exists(self, slug: str) -> bool:
        return self.db.scalar(select(Organization.id).where(Organization.slug == slug)) is not None

    def create_user(self, *, name: str, email: str, password_hash: str) -> User:
        user = User(name=name, email=email, password_hash=password_hash)
        self.db.add(user)
        self.db.flush()
        return user

    def create_organization(self, *, name: str, slug: str) -> Organization:
        organization = Organization(name=name, slug=slug)
        self.db.add(organization)
        self.db.flush()
        return organization

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
