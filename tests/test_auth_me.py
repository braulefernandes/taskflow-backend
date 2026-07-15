import uuid
from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.jwt import create_access_token
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Organization, OrganizationMember, OrganizationRole, User


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        yield session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def create_account(
    db_session: Session,
    *,
    is_active: bool = True,
    membership_active: bool = True,
) -> tuple[User, Organization, OrganizationMember]:
    user = User(
        name="Ana Silva",
        email="ana@example.com",
        password_hash=get_password_hash("Senha123"),
        is_active=is_active,
    )
    organization = Organization(name="Acme Suporte", slug="acme-suporte")
    membership = OrganizationMember(
        user=user,
        organization=organization,
        role=OrganizationRole.ADMIN,
        is_active=membership_active,
    )
    db_session.add_all([user, organization, membership])
    db_session.commit()
    return user, organization, membership


def token_for(user: User, membership: OrganizationMember, **kwargs) -> str:
    return create_access_token(
        subject=str(user.id),
        organization_id=str(membership.organization_id),
        role=membership.role.value,
        **kwargs,
    )


def get_me(client: TestClient, token: str | None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.get("/api/v1/auth/me", headers=headers)


def assert_not_authenticated(response) -> None:
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "not_authenticated",
            "message": "Nao autenticado.",
        }
    }


def test_auth_me_with_valid_token(client: TestClient, db_session: Session) -> None:
    user, _organization, membership = create_account(db_session)

    response = get_me(client, token_for(user, membership))

    assert response.status_code == 200


def test_auth_me_response_contains_user(
    client: TestClient, db_session: Session
) -> None:
    user, _organization, membership = create_account(db_session)

    response = get_me(client, token_for(user, membership))
    data = response.json()

    assert data["user"] == {
        "id": str(user.id),
        "name": "Ana Silva",
        "email": "ana@example.com",
        "avatar_url": None,
        "is_active": True,
    }


def test_auth_me_response_contains_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    user, organization, membership = create_account(db_session)

    response = get_me(client, token_for(user, membership))
    data = response.json()

    assert data["organization"] == {
        "id": str(organization.id),
        "name": "Acme Suporte",
        "slug": "acme-suporte",
    }


def test_auth_me_response_contains_role(
    client: TestClient, db_session: Session
) -> None:
    user, _organization, membership = create_account(db_session)

    response = get_me(client, token_for(user, membership))

    assert response.json()["membership"]["role"] == "ADMIN"
    assert response.json()["membership"]["is_active"] is True


def test_auth_me_response_does_not_expose_hash_or_token(
    client: TestClient,
    db_session: Session,
) -> None:
    user, _organization, membership = create_account(db_session)

    response = get_me(client, token_for(user, membership))
    response_text = response.text

    assert "password_hash" not in response_text
    assert "access_token" not in response_text
    assert "pbkdf2_sha256" not in response_text


def test_auth_me_without_token(client: TestClient) -> None:
    response = get_me(client, None)

    assert_not_authenticated(response)


def test_auth_me_with_invalid_token(client: TestClient) -> None:
    response = get_me(client, "token.invalido.assinatura")

    assert_not_authenticated(response)


def test_auth_me_with_expired_token(client: TestClient, db_session: Session) -> None:
    user, _organization, membership = create_account(db_session)
    token = token_for(user, membership, expires_delta=timedelta(minutes=-1))

    response = get_me(client, token)

    assert_not_authenticated(response)


def test_auth_me_with_invalid_subject(client: TestClient, db_session: Session) -> None:
    _user, _organization, membership = create_account(db_session)
    token = create_access_token(
        subject="not-a-uuid",
        organization_id=str(membership.organization_id),
        role="ADMIN",
    )

    response = get_me(client, token)

    assert_not_authenticated(response)


def test_auth_me_rejects_missing_user(client: TestClient) -> None:
    token = create_access_token(
        subject=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        role="ADMIN",
    )

    response = get_me(client, token)

    assert_not_authenticated(response)


def test_auth_me_rejects_user_without_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    user = User(
        name="Sem Membership",
        email="sem-membership@example.com",
        password_hash=get_password_hash("Senha123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token(
        subject=str(user.id),
        organization_id=str(uuid.uuid4()),
        role="ADMIN",
    )

    response = get_me(client, token)

    assert_not_authenticated(response)


def test_auth_me_rejects_user_deactivated_after_token_issue(
    client: TestClient,
    db_session: Session,
) -> None:
    user, _organization, membership = create_account(db_session)
    token = token_for(user, membership)
    user.is_active = False
    db_session.commit()

    response = get_me(client, token)

    assert_not_authenticated(response)


def test_auth_me_rejects_inactive_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    user, _organization, membership = create_account(db_session)
    token = token_for(user, membership)
    membership.is_active = False
    db_session.commit()

    response = get_me(client, token)

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "membership_inactive",
            "message": "Membership inativo.",
        }
    }


def test_auth_me_does_not_infer_access_to_another_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    user, _organization, membership = create_account(db_session)
    token = create_access_token(
        subject=str(user.id),
        organization_id=str(uuid.uuid4()),
        role=membership.role.value,
    )

    response = get_me(client, token)

    assert_not_authenticated(response)
