import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
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
    role: OrganizationRole = OrganizationRole.ADMIN,
    email: str | None = None,
    organization: Organization | None = None,
    membership_active: bool = True,
) -> tuple[User, Organization, OrganizationMember]:
    unique = uuid.uuid4()
    user = User(
        name=f"Usuário {role.value}",
        email=email or f"{unique}@example.com",
        password_hash=get_password_hash("Senha123"),
        is_active=True,
    )
    organization = organization or Organization(
        name=f"Organização {unique}",
        slug=f"org-{unique}",
    )
    membership = OrganizationMember(
        user=user,
        organization=organization,
        role=role,
        is_active=membership_active,
    )
    db_session.add_all([user, organization, membership])
    db_session.commit()
    return user, organization, membership


def token_for(user: User, membership: OrganizationMember) -> str:
    return create_access_token(
        subject=str(user.id),
        organization_id=str(membership.organization_id),
        role=membership.role.value,
    )


def headers_for(user: User, membership: OrganizationMember) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user, membership)}"}


def member_payload(**overrides) -> dict[str, str]:
    payload = {
        "name": "Novo Membro",
        "email": "novo@example.com",
        "role": "AGENT",
        "temporary_password": "Temporaria123",
    }
    payload.update(overrides)
    return payload


def test_admin_lists_only_members_from_current_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, admin_membership = create_account(db_session)
    create_account(db_session, role=OrganizationRole.AGENT, organization=organization)
    create_account(db_session, role=OrganizationRole.REQUESTER)

    response = client.get(
        "/api/v1/members", headers=headers_for(admin, admin_membership)
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 2


@pytest.mark.parametrize(
    "role",
    [OrganizationRole.MANAGER, OrganizationRole.AGENT, OrganizationRole.REQUESTER],
)
def test_non_admin_roles_cannot_manage_members(
    role: OrganizationRole,
    client: TestClient,
    db_session: Session,
) -> None:
    user, _organization, membership = create_account(db_session, role=role)

    response = client.get("/api/v1/members", headers=headers_for(user, membership))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


@pytest.mark.parametrize(
    ("method", "path_suffix", "payload"),
    [
        ("post", "", member_payload(email="negado@example.com")),
        ("patch", "/self", {"role": "ADMIN"}),
        ("patch", "/self/status", {"is_active": False}),
    ],
)
def test_non_admin_cannot_mutate_members(
    method: str,
    path_suffix: str,
    payload: dict[str, object],
    client: TestClient,
    db_session: Session,
) -> None:
    user, _organization, membership = create_account(
        db_session,
        role=OrganizationRole.MANAGER,
    )
    path = "/api/v1/members"
    if path_suffix:
        path += path_suffix.replace("self", str(membership.id))

    response = client.request(
        method,
        path,
        headers=headers_for(user, membership),
        json=payload,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_inactive_membership_cannot_access_member_management(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, membership = create_account(
        db_session,
        membership_active=False,
    )

    response = client.get(
        "/api/v1/members",
        headers=headers_for(admin, membership),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "membership_inactive"


def test_admin_creates_user_and_membership_without_exposing_hash(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, admin_membership = create_account(db_session)

    response = client.post(
        "/api/v1/members",
        headers=headers_for(admin, admin_membership),
        json=member_payload(),
    )

    assert response.status_code == 201
    assert response.json()["email"] == "novo@example.com"
    assert response.json()["role"] == "AGENT"
    assert "password" not in response.text
    user = db_session.scalar(select(User).where(User.email == "novo@example.com"))
    assert user is not None
    assert (
        db_session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id == organization.id,
            )
        )
        is not None
    )


def test_existing_user_is_associated_without_duplication(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, admin_membership = create_account(db_session)
    existing_user, _other_org, _other_membership = create_account(
        db_session,
        email="existente@example.com",
    )
    original_hash = existing_user.password_hash

    response = client.post(
        "/api/v1/members",
        headers=headers_for(admin, admin_membership),
        json=member_payload(email=" EXISTENTE@Example.COM ", name="Nome Ignorado"),
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == str(existing_user.id)
    assert response.json()["name"] == existing_user.name
    assert existing_user.password_hash == original_hash
    assert db_session.scalar(select(func.count()).select_from(User)) == 2


def test_duplicate_membership_is_rejected(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, admin_membership = create_account(
        db_session,
        email="admin@example.com",
    )

    response = client.post(
        "/api/v1/members",
        headers=headers_for(admin, admin_membership),
        json=member_payload(email="ADMIN@example.com"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "membership_already_exists"


def test_admin_changes_member_role(client: TestClient, db_session: Session) -> None:
    admin, organization, admin_membership = create_account(db_session)
    _user, _organization, membership = create_account(
        db_session,
        role=OrganizationRole.AGENT,
        organization=organization,
    )

    response = client.patch(
        f"/api/v1/members/{membership.id}",
        headers=headers_for(admin, admin_membership),
        json={"role": "MANAGER"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "MANAGER"


def test_admin_deactivates_and_activates_member(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, admin_membership = create_account(db_session)
    _user, _organization, membership = create_account(
        db_session,
        role=OrganizationRole.AGENT,
        organization=organization,
    )

    deactivated = client.patch(
        f"/api/v1/members/{membership.id}/status",
        headers=headers_for(admin, admin_membership),
        json={"is_active": False},
    )
    activated = client.patch(
        f"/api/v1/members/{membership.id}/status",
        headers=headers_for(admin, admin_membership),
        json={"is_active": True},
    )

    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True


def test_member_from_another_organization_is_hidden(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, admin_membership = create_account(db_session)
    _other_user, _other_org, other_membership = create_account(db_session)

    response = client.get(
        f"/api/v1/members/{other_membership.id}",
        headers=headers_for(admin, admin_membership),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


@pytest.mark.parametrize(
    ("path_suffix", "payload"),
    [
        ("", {"role": "MANAGER"}),
        ("/status", {"is_active": False}),
    ],
)
def test_member_from_another_organization_cannot_be_mutated(
    path_suffix: str,
    payload: dict[str, object],
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, admin_membership = create_account(db_session)
    _other_user, _other_org, other_membership = create_account(
        db_session,
        role=OrganizationRole.AGENT,
    )

    response = client.patch(
        f"/api/v1/members/{other_membership.id}{path_suffix}",
        headers=headers_for(admin, admin_membership),
        json=payload,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


@pytest.mark.parametrize("operation", ["role", "status"])
def test_last_active_admin_is_protected(
    operation: str,
    client: TestClient,
    db_session: Session,
) -> None:
    admin, _organization, membership = create_account(db_session)
    path = f"/api/v1/members/{membership.id}"
    payload = {"role": "MANAGER"}
    if operation == "status":
        path += "/status"
        payload = {"is_active": False}

    response = client.patch(path, headers=headers_for(admin, membership), json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_active_admin"


def test_listing_supports_search_filters_and_pagination(
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, admin_membership = create_account(db_session)
    create_account(
        db_session,
        role=OrganizationRole.AGENT,
        email="busca@example.com",
        organization=organization,
    )
    create_account(
        db_session,
        role=OrganizationRole.REQUESTER,
        organization=organization,
        membership_active=False,
    )

    filtered = client.get(
        "/api/v1/members?search=BUSCA&role=AGENT&is_active=true",
        headers=headers_for(admin, admin_membership),
    )
    paginated = client.get(
        "/api/v1/members?page=2&page_size=1",
        headers=headers_for(admin, admin_membership),
    )

    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["email"] == "busca@example.com"
    assert paginated.status_code == 200
    assert paginated.json()["total"] == 3
    assert len(paginated.json()["items"]) == 1
    assert paginated.json()["page"] == 2
