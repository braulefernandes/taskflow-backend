import uuid
from collections.abc import Generator

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
    user_active: bool = True,
) -> tuple[User, OrganizationMember]:
    unique = uuid.uuid4()
    user = User(
        name="Nome Original",
        email=f"{unique}@example.com",
        password_hash=get_password_hash("Senha123"),
        is_active=user_active,
    )
    organization = Organization(name="Organizacao", slug=f"org-{unique}")
    membership = OrganizationMember(
        user=user,
        organization=organization,
        role=OrganizationRole.REQUESTER,
        is_active=True,
    )
    db_session.add_all([user, organization, membership])
    db_session.commit()
    return user, membership


def auth_headers(user: User, membership: OrganizationMember) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        organization_id=str(membership.organization_id),
        role=membership.role.value,
    )
    return {"Authorization": f"Bearer {token}"}


def test_user_updates_and_normalizes_own_name(
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)

    response = client.patch(
        "/api/v1/users/me",
        headers=auth_headers(user, membership),
        json={"name": "  Novo   Nome  "},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Novo Nome"
    assert user.name == "Novo Nome"


def test_partial_avatar_update_preserves_name(
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)

    response = client.patch(
        "/api/v1/users/me",
        headers=auth_headers(user, membership),
        json={"avatar_url": "https://cdn.example.com/avatar.png"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Nome Original"
    assert response.json()["avatar_url"] == "https://cdn.example.com/avatar.png"


@pytest.mark.parametrize("invalid_name", ["", "   ", None])
def test_invalid_name_is_rejected(
    invalid_name: str | None,
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)

    response = client.patch(
        "/api/v1/users/me",
        headers=auth_headers(user, membership),
        json={"name": invalid_name},
    )

    assert response.status_code == 422
    assert user.name == "Nome Original"


def test_valid_avatar_can_be_set_and_removed(
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)
    headers = auth_headers(user, membership)

    created = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"avatar_url": "https://example.com/avatar.jpg"},
    )
    removed = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"avatar_url": None},
    )

    assert created.status_code == 200
    assert created.json()["avatar_url"] == "https://example.com/avatar.jpg"
    assert removed.status_code == 200
    assert removed.json()["avatar_url"] is None


@pytest.mark.parametrize(
    "invalid_avatar",
    ["not-a-url", "ftp://example.com/avatar.png", "//example.com/avatar.png"],
)
def test_invalid_avatar_is_rejected(
    invalid_avatar: str,
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)

    response = client.patch(
        "/api/v1/users/me",
        headers=auth_headers(user, membership),
        json={"avatar_url": invalid_avatar},
    )

    assert response.status_code == 422


def test_profile_update_requires_authentication(client: TestClient) -> None:
    response = client.patch("/api/v1/users/me", json={"name": "Novo Nome"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "outro@example.com"),
        ("is_active", False),
        ("password_hash", "hash-forjado"),
        ("role", "ADMIN"),
        ("organization_id", str(uuid.uuid4())),
        ("membership", {}),
        ("id", str(uuid.uuid4())),
        ("created_at", "2026-01-01T00:00:00Z"),
        ("updated_at", "2026-01-01T00:00:00Z"),
    ],
)
def test_administrative_fields_are_rejected(
    field: str,
    value: object,
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)

    response = client.patch(
        "/api/v1/users/me",
        headers=auth_headers(user, membership),
        json={field: value},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_profile_response_never_exposes_password_hash(
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)

    response = client.patch(
        "/api/v1/users/me",
        headers=auth_headers(user, membership),
        json={"name": "Nome Publico"},
    )

    assert response.status_code == 200
    assert "password" not in response.text
    assert "hash" not in response.text


def test_auth_me_reflects_profile_update(
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)
    headers = auth_headers(user, membership)

    updated = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"name": "Nome Atualizado", "avatar_url": "https://example.com/new.png"},
    )
    me_response = client.get("/api/v1/auth/me", headers=headers)

    assert updated.status_code == 200
    assert me_response.status_code == 200
    assert me_response.json()["user"]["name"] == "Nome Atualizado"
    assert me_response.json()["user"]["avatar_url"] == "https://example.com/new.png"


def test_inactive_user_cannot_update_profile(
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session, user_active=False)

    response = client.patch(
        "/api/v1/users/me",
        headers=auth_headers(user, membership),
        json={"name": "Nome Bloqueado"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert user.name == "Nome Original"
