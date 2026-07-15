from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Organization, OrganizationMember, OrganizationRole, User
from app.repositories.auth import AuthRepository


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


def valid_payload(**overrides) -> dict[str, str]:
    payload = {
        "user_name": " Ana Silva ",
        "email": " ANA@Example.COM ",
        "password": "Senha123",
        "organization_name": " Acme Suporte ",
    }
    payload.update(overrides)
    return payload


def post_register(client: TestClient, **overrides):
    return client.post("/api/v1/auth/register", json=valid_payload(**overrides))


def test_register_valid_account_returns_created_response(client: TestClient) -> None:
    response = post_register(client)

    assert response.status_code == 201
    data = response.json()
    assert data["user"]["name"] == "Ana Silva"
    assert data["user"]["email"] == "ana@example.com"
    assert data["organization"]["name"] == "Acme Suporte"
    assert data["organization"]["slug"] == "acme-suporte"
    assert data["membership"]["role"] == "ADMIN"
    assert data["membership"]["is_active"] is True
    assert "password_hash" not in data["user"]
    assert "password" not in str(data)


def test_register_persists_user_organization_and_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    post_register(client)

    user = db_session.scalar(select(User).where(User.email == "ana@example.com"))
    organization = db_session.scalar(
        select(Organization).where(Organization.slug == "acme-suporte")
    )
    membership = db_session.scalar(select(OrganizationMember))

    assert user is not None
    assert organization is not None
    assert membership is not None
    assert membership.user_id == user.id
    assert membership.organization_id == organization.id
    assert membership.role is OrganizationRole.ADMIN
    assert membership.is_active is True


def test_register_stores_password_as_hash(
    client: TestClient, db_session: Session
) -> None:
    post_register(client, password="Senha123")

    user = db_session.scalar(select(User).where(User.email == "ana@example.com"))

    assert user is not None
    assert user.password_hash != "Senha123"
    assert user.password_hash.startswith("pbkdf2_sha256$")


def test_register_rejects_duplicate_email(
    client: TestClient, db_session: Session
) -> None:
    post_register(client)
    response = post_register(
        client, user_name="Outra Pessoa", organization_name="Outra Org"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"
    assert (
        db_session.scalar(select(User).where(User.email == "ana@example.com")).email
        == "ana@example.com"
    )
    assert len(db_session.scalars(select(User)).all()) == 1


def test_register_rejects_invalid_password(
    client: TestClient, db_session: Session
) -> None:
    response = post_register(client, password="senhafraca")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert db_session.scalar(select(User)) is None


def test_register_rejects_invalid_organization_name(
    client: TestClient, db_session: Session
) -> None:
    response = post_register(client, organization_name="   ")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert db_session.scalar(select(Organization)) is None


def test_register_generates_unique_slug_on_collision(
    client: TestClient, db_session: Session
) -> None:
    first_response = post_register(
        client, email="ana@example.com", organization_name="Café Central"
    )
    second_response = post_register(
        client, email="bia@example.com", organization_name="Cafe Central"
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["organization"]["slug"] == "cafe-central"
    assert second_response.json()["organization"]["slug"] == "cafe-central-2"
    assert db_session.scalars(
        select(Organization.slug).order_by(Organization.slug)
    ).all() == [
        "cafe-central",
        "cafe-central-2",
    ]


def test_register_rolls_back_when_membership_creation_fails(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    def fail_create_membership(self, *, user, organization, role):
        raise SQLAlchemyError("forced membership failure")

    monkeypatch.setattr(AuthRepository, "create_membership", fail_create_membership)

    response = post_register(client)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "registration_persistence_error"
    assert db_session.scalar(select(User)) is None
    assert db_session.scalar(select(Organization)) is None
    assert db_session.scalar(select(OrganizationMember)) is None
