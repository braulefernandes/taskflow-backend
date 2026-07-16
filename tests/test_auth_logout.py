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


def create_account(db_session: Session) -> tuple[User, OrganizationMember]:
    user = User(
        name="Ana Silva",
        email="ana@example.com",
        password_hash=get_password_hash("Senha123"),
        is_active=True,
    )
    organization = Organization(name="Acme Suporte", slug="acme-suporte")
    membership = OrganizationMember(
        user=user,
        organization=organization,
        role=OrganizationRole.ADMIN,
        is_active=True,
    )
    db_session.add_all([user, organization, membership])
    db_session.commit()
    return user, membership


def token_for(user: User, membership: OrganizationMember) -> str:
    return create_access_token(
        subject=str(user.id),
        organization_id=str(membership.organization_id),
        role=membership.role.value,
    )


def post_logout(client: TestClient, token: str | None):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/api/v1/auth/logout", headers=headers)


def assert_not_authenticated(response) -> None:
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "not_authenticated",
            "message": "Não autenticado.",
        }
    }


def test_logout_authenticated(client: TestClient, db_session: Session) -> None:
    user, membership = create_account(db_session)

    response = post_logout(client, token_for(user, membership))

    assert response.status_code == 200


def test_logout_without_token(client: TestClient) -> None:
    response = post_logout(client, None)

    assert_not_authenticated(response)


def test_logout_with_invalid_token(client: TestClient) -> None:
    response = post_logout(client, "token.invalido.assinatura")

    assert_not_authenticated(response)


def test_logout_response_contract(client: TestClient, db_session: Session) -> None:
    user, membership = create_account(db_session)

    response = post_logout(client, token_for(user, membership))

    assert response.json() == {
        "message": "Logout registrado no cliente. Descarte o token localmente.",
        "token_revoked": False,
    }


def test_logout_is_stateless_and_does_not_revoke_token(
    client: TestClient,
    db_session: Session,
) -> None:
    user, membership = create_account(db_session)
    token = token_for(user, membership)

    first_response = post_logout(client, token)
    second_response = post_logout(client, token)
    me_response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert me_response.status_code == 200


def test_readme_documents_stateless_logout() -> None:
    with open("README.md", encoding="utf-8") as readme_file:
        readme = readme_file.read()

    assert "POST /api/v1/auth/logout" in readme
    assert "JWT stateless" in readme
    assert "não revoga" in readme
    assert "descartar o token" in readme
