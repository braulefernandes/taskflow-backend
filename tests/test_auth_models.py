from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import (
    Organization,
    OrganizationMember,
    OrganizationRole,
    PasswordResetToken,
    User,
)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        yield session

    Base.metadata.drop_all(bind=engine)


def make_user(email: str = "ana@example.com") -> User:
    return User(
        name="Ana Silva",
        email=email,
        password_hash="hashed-password",
    )


def make_organization(slug: str = "acme") -> Organization:
    return Organization(name="Acme", slug=slug)


def test_create_user(db_session: Session) -> None:
    user = make_user()

    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.is_active is True
    assert "hashed-password" not in repr(user)


def test_user_email_must_be_unique(db_session: Session) -> None:
    db_session.add_all([make_user(), make_user()])

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_organization(db_session: Session) -> None:
    organization = make_organization()

    db_session.add(organization)
    db_session.commit()

    assert organization.id is not None
    assert organization.slug == "acme"


def test_organization_slug_must_be_unique(db_session: Session) -> None:
    db_session.add_all([make_organization(), make_organization()])

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_membership_and_relationships(db_session: Session) -> None:
    user = make_user()
    organization = make_organization()
    membership = OrganizationMember(
        user=user,
        organization=organization,
        role=OrganizationRole.ADMIN,
    )

    db_session.add(membership)
    db_session.commit()

    assert membership.id is not None
    assert membership.role is OrganizationRole.ADMIN
    assert membership in user.memberships
    assert membership in organization.memberships
    assert membership.user is user
    assert membership.organization is organization


def test_duplicate_membership_is_not_allowed(db_session: Session) -> None:
    user = make_user()
    organization = make_organization()
    db_session.add_all(
        [
            OrganizationMember(
                user=user, organization=organization, role=OrganizationRole.ADMIN
            ),
            OrganizationMember(
                user=user, organization=organization, role=OrganizationRole.AGENT
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_create_password_reset_token(db_session: Session) -> None:
    user = make_user()
    token = PasswordResetToken(
        user=user,
        token_hash="hashed-reset-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    db_session.add(token)
    db_session.commit()

    assert token.id is not None
    assert token.token_hash == "hashed-reset-token"
    assert token.used_at is None
    assert token.user is user
    assert token in user.password_reset_tokens
