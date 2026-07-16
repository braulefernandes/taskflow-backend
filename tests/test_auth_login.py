from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import jwt as jwt_module
from app.core.jwt import (
    InvalidTokenError,
    TokenExpiredError,
    base64url_encode,
    create_access_token,
    decode_access_token,
)
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Organization, OrganizationMember, OrganizationRole, User
from app.services import auth as auth_service_module


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
    email: str = "ana@example.com",
    password: str = "Senha123",
    is_active: bool = True,
    membership_active: bool = True,
) -> tuple[User, Organization, OrganizationMember]:
    user = User(
        name="Ana Silva",
        email=email,
        password_hash=get_password_hash(password),
        is_active=is_active,
    )
    organization = Organization(name="Acme Suporte", slug=f"acme-{email.split('@')[0]}")
    membership = OrganizationMember(
        user=user,
        organization=organization,
        role=OrganizationRole.ADMIN,
        is_active=membership_active,
    )
    db_session.add_all([user, organization, membership])
    db_session.commit()
    return user, organization, membership


def post_login(
    client: TestClient, *, email: str = "ana@example.com", password: str = "Senha123"
):
    return client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


def assert_invalid_credentials(response) -> None:
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_credentials",
            "message": "Credenciais inválidas.",
        }
    }


def test_login_valid_credentials_returns_access_token(
    client: TestClient,
    db_session: Session,
) -> None:
    create_account(db_session)

    response = post_login(client)

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 1800
    assert isinstance(data["access_token"], str)
    assert data["access_token"].count(".") == 2
    assert "password" not in str(data)
    assert "password_hash" not in str(data)


def test_login_normalizes_email(client: TestClient, db_session: Session) -> None:
    create_account(db_session, email="ana@example.com")

    response = post_login(client, email=" ANA@Example.COM ")

    assert response.status_code == 200


def test_login_rejects_invalid_password(
    client: TestClient, db_session: Session
) -> None:
    create_account(db_session)

    response = post_login(client, password="SenhaErrada123")

    assert_invalid_credentials(response)


def test_login_rejects_unknown_email(client: TestClient) -> None:
    response = post_login(client, email="ninguem@example.com")

    assert_invalid_credentials(response)


def test_invalid_credentials_share_same_message(
    client: TestClient,
    db_session: Session,
) -> None:
    create_account(db_session)

    invalid_password = post_login(client, password="SenhaErrada123").json()
    unknown_email = post_login(client, email="ninguem@example.com").json()

    assert invalid_password == unknown_email


def test_login_rejects_inactive_user(client: TestClient, db_session: Session) -> None:
    create_account(db_session, is_active=False)

    response = post_login(client)

    assert_invalid_credentials(response)


def test_login_rejects_user_without_active_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    create_account(db_session, membership_active=False)

    response = post_login(client)

    assert_invalid_credentials(response)


def test_login_token_contains_subject_and_context(
    client: TestClient,
    db_session: Session,
) -> None:
    user, _organization, membership = create_account(db_session)

    response = post_login(client)
    payload = decode_access_token(response.json()["access_token"])

    assert payload["sub"] == str(user.id)
    assert payload["org"] == str(membership.organization_id)
    assert payload["role"] == "ADMIN"
    assert "email" not in payload
    assert "password_hash" not in payload


def test_expired_token_is_rejected() -> None:
    token = create_access_token(
        subject="user-id",
        expires_delta=timedelta(minutes=-1),
        issued_at=datetime.now(UTC),
    )

    with pytest.raises(TokenExpiredError):
        decode_access_token(token)


def test_invalid_token_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("token.invalido.assinatura")


def test_token_header_algorithm_does_not_control_validation() -> None:
    token = create_access_token(subject="user-id")
    _header, payload, signature = token.split(".", 2)
    forged_header = base64url_encode(b'{"typ":"JWT","alg":"none"}')

    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{forged_header}.{payload}.{signature}")


def test_login_respects_token_duration_from_settings(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    create_account(db_session)
    monkeypatch.setattr(auth_service_module.settings, "access_token_expire_minutes", 2)
    monkeypatch.setattr(jwt_module.settings, "access_token_expire_minutes", 2)

    response = post_login(client)
    payload = decode_access_token(response.json()["access_token"])

    assert response.json()["expires_in"] == 120
    assert payload["exp"] - payload["iat"] == 120


def test_login_does_not_persist_sensitive_data_in_response(
    client: TestClient,
    db_session: Session,
) -> None:
    create_account(db_session)

    response = post_login(client)

    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "token_type", "expires_in"}
    assert (
        db_session.scalar(select(User).where(User.email == "ana@example.com"))
        is not None
    )
