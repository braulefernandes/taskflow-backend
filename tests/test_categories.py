import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.jwt import create_access_token
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Category,
    Organization,
    OrganizationMember,
    OrganizationRole,
    User,
)


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
    role: OrganizationRole = OrganizationRole.ADMIN,
    organization: Organization | None = None,
) -> tuple[User, Organization, OrganizationMember]:
    unique = uuid.uuid4()
    user = User(
        name=f"Usuario {role.value}",
        email=f"{unique}@example.com",
        password_hash=get_password_hash("Senha123"),
        is_active=True,
    )
    organization = organization or Organization(
        name=f"Organizacao {unique}",
        slug=f"org-{unique}",
    )
    membership = OrganizationMember(
        user=user,
        organization=organization,
        role=role,
        is_active=True,
    )
    db_session.add_all([user, organization, membership])
    db_session.commit()
    return user, organization, membership


def headers_for(user: User, membership: OrganizationMember) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        organization_id=str(membership.organization_id),
        role=membership.role.value,
    )
    return {"Authorization": f"Bearer {token}"}


def create_category(
    db_session: Session,
    organization: Organization,
    *,
    name: str,
    is_active: bool = True,
) -> Category:
    category = Category(
        organization=organization,
        name=name,
        normalized_name=name.casefold(),
        description=f"Descricao {name}",
        is_active=is_active,
    )
    db_session.add(category)
    db_session.commit()
    return category


def test_admin_creates_normalized_category(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, membership = create_account(db_session)

    response = client.post(
        "/api/v1/categories",
        headers=headers_for(admin, membership),
        json={"name": "  Suporte   Tecnico  ", "description": "  Atendimento  "},
    )

    assert response.status_code == 201
    assert response.json()["organization_id"] == str(organization.id)
    assert response.json()["name"] == "Suporte Tecnico"
    assert response.json()["description"] == "Atendimento"
    assert response.json()["is_active"] is True


@pytest.mark.parametrize(
    "role",
    [OrganizationRole.MANAGER, OrganizationRole.AGENT, OrganizationRole.REQUESTER],
)
def test_non_admin_roles_cannot_create_category(
    role: OrganizationRole,
    client: TestClient,
    db_session: Session,
) -> None:
    user, _organization, membership = create_account(db_session, role=role)

    response = client.post(
        "/api/v1/categories",
        headers=headers_for(user, membership),
        json={"name": "Financeiro"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


@pytest.mark.parametrize(
    ("path_suffix", "payload"),
    [
        ("", {"name": "Nome Negado"}),
        ("/status", {"is_active": False}),
    ],
)
def test_non_admin_roles_cannot_mutate_category(
    path_suffix: str,
    payload: dict[str, object],
    client: TestClient,
    db_session: Session,
) -> None:
    user, organization, membership = create_account(
        db_session,
        role=OrganizationRole.MANAGER,
    )
    category = create_category(db_session, organization, name="Protegida")

    response = client.patch(
        f"/api/v1/categories/{category.id}{path_suffix}",
        headers=headers_for(user, membership),
        json=payload,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_duplicate_name_in_same_organization_is_case_insensitive(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, membership = create_account(db_session)
    headers = headers_for(admin, membership)
    first = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": "Recursos Humanos"},
    )

    duplicate = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": "  RECURSOS   HUMANOS "},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "category_already_exists"


def test_same_name_is_allowed_in_different_organizations(
    client: TestClient,
    db_session: Session,
) -> None:
    admin_a, _org_a, membership_a = create_account(db_session)
    admin_b, _org_b, membership_b = create_account(db_session)

    response_a = client.post(
        "/api/v1/categories",
        headers=headers_for(admin_a, membership_a),
        json={"name": "Financeiro"},
    )
    response_b = client.post(
        "/api/v1/categories",
        headers=headers_for(admin_b, membership_b),
        json={"name": "financeiro"},
    )

    assert response_a.status_code == 201
    assert response_b.status_code == 201


def test_list_is_isolated_by_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    user_a, org_a, membership_a = create_account(
        db_session,
        role=OrganizationRole.REQUESTER,
    )
    _user_b, org_b, _membership_b = create_account(db_session)
    category_a = create_category(db_session, org_a, name="Categoria A")
    create_category(db_session, org_b, name="Categoria B")

    response = client.get(
        "/api/v1/categories",
        headers=headers_for(user_a, membership_a),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(category_a.id)]


def test_admin_edits_category(client: TestClient, db_session: Session) -> None:
    admin, organization, membership = create_account(db_session)
    category = create_category(db_session, organization, name="Nome Antigo")

    response = client.patch(
        f"/api/v1/categories/{category.id}",
        headers=headers_for(admin, membership),
        json={"name": "  Nome Novo ", "description": None},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Nome Novo"
    assert response.json()["description"] is None


def test_admin_deactivates_and_activates_category(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, membership = create_account(db_session)
    category = create_category(db_session, organization, name="Operacoes")
    headers = headers_for(admin, membership)

    deactivated = client.patch(
        f"/api/v1/categories/{category.id}/status",
        headers=headers,
        json={"is_active": False},
    )
    activated = client.patch(
        f"/api/v1/categories/{category.id}/status",
        headers=headers,
        json={"is_active": True},
    )

    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    assert db_session.get(Category, category.id) is not None


def test_form_listing_contains_only_active_categories(
    client: TestClient,
    db_session: Session,
) -> None:
    requester, organization, membership = create_account(
        db_session,
        role=OrganizationRole.REQUESTER,
    )
    active = create_category(db_session, organization, name="Ativa")
    create_category(db_session, organization, name="Inativa", is_active=False)

    response = client.get(
        "/api/v1/categories",
        headers=headers_for(requester, membership),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(active.id)]


def test_admin_listing_can_include_inactive_categories(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, membership = create_account(db_session)
    create_category(db_session, organization, name="Ativa")
    create_category(db_session, organization, name="Inativa", is_active=False)

    response = client.get(
        "/api/v1/categories?include_inactive=true",
        headers=headers_for(admin, membership),
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_non_admin_cannot_request_inactive_categories(
    client: TestClient,
    db_session: Session,
) -> None:
    requester, _organization, membership = create_account(
        db_session,
        role=OrganizationRole.REQUESTER,
    )

    response = client.get(
        "/api/v1/categories?include_inactive=true",
        headers=headers_for(requester, membership),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_category_id_from_another_organization_is_hidden(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, membership = create_account(db_session)
    _other_admin, other_org, _other_membership = create_account(db_session)
    external_category = create_category(db_session, other_org, name="Externa")

    response = client.get(
        f"/api/v1/categories/{external_category.id}",
        headers=headers_for(admin, membership),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_category_from_another_organization_cannot_be_edited(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, membership = create_account(db_session)
    _other_admin, other_org, _other_membership = create_account(db_session)
    external_category = create_category(db_session, other_org, name="Externa")

    response = client.patch(
        f"/api/v1/categories/{external_category.id}",
        headers=headers_for(admin, membership),
        json={"name": "Tentativa"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_inactive_category_detail_is_hidden_from_non_admin(
    client: TestClient,
    db_session: Session,
) -> None:
    requester, organization, membership = create_account(
        db_session,
        role=OrganizationRole.REQUESTER,
    )
    category = create_category(
        db_session,
        organization,
        name="Inativa",
        is_active=False,
    )

    response = client.get(
        f"/api/v1/categories/{category.id}",
        headers=headers_for(requester, membership),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


@pytest.mark.parametrize("invalid_name", ["", "   ", None])
def test_category_name_is_required_and_validated(
    invalid_name: str | None,
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, membership = create_account(db_session)

    response = client.post(
        "/api/v1/categories",
        headers=headers_for(admin, membership),
        json={"name": invalid_name},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_category_has_no_physical_delete_endpoint(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, membership = create_account(db_session)
    category = create_category(db_session, organization, name="Persistente")

    response = client.delete(
        f"/api/v1/categories/{category.id}",
        headers=headers_for(admin, membership),
    )

    assert response.status_code == 405
    assert (
        db_session.scalar(select(Category).where(Category.id == category.id))
        is not None
    )
