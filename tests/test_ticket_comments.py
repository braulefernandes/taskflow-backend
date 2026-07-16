import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.jwt import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Category,
    Organization,
    OrganizationMember,
    OrganizationRole,
    Ticket,
    TicketComment,
    TicketStatus,
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
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
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
    db: Session,
    role: OrganizationRole,
    organization: Organization | None = None,
) -> tuple[User, Organization, OrganizationMember]:
    unique = uuid.uuid4()
    user = User(
        name=f"Usuário {role.value}",
        email=f"{unique}@example.com",
        password_hash="secret-hash",
    )
    organization = organization or Organization(
        name="Organização", slug=f"org-{unique}"
    )
    membership = OrganizationMember(
        user=user, organization=organization, role=role, is_active=True
    )
    db.add_all([user, organization, membership])
    db.commit()
    return user, organization, membership


def auth_headers(user: User, membership: OrganizationMember) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        organization_id=str(membership.organization_id),
        role=membership.role.value,
    )
    return {"Authorization": f"Bearer {token}"}


def create_ticket(
    db: Session,
    organization: Organization,
    requester: User,
    *,
    assignee: User | None = None,
    status: TicketStatus = TicketStatus.PENDING,
) -> Ticket:
    unique = uuid.uuid4()
    category = Category(
        organization=organization,
        name=f"Categoria {unique}",
        normalized_name=str(unique),
    )
    ticket = Ticket(
        organization=organization,
        category=category,
        requester=requester,
        assignee=assignee,
        title="Ticket",
        description="Descrição",
        status=status,
    )
    db.add(ticket)
    db.commit()
    return ticket


def comments_path(ticket: Ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/comments"


@pytest.mark.parametrize("role", [OrganizationRole.ADMIN, OrganizationRole.MANAGER])
def test_management_comments_on_any_organization_ticket(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    actor, organization, membership = create_account(db_session, role)
    requester, _, _ = create_account(
        db_session, OrganizationRole.REQUESTER, organization
    )
    ticket = create_ticket(db_session, organization, requester)

    response = client.post(
        comments_path(ticket),
        headers=auth_headers(actor, membership),
        json={"content": "Comentário gerencial"},
    )

    assert response.status_code == 201
    assert response.json()["author"]["id"] == str(actor.id)


def test_agent_comments_on_assigned_ticket(
    client: TestClient, db_session: Session
) -> None:
    agent, organization, membership = create_account(db_session, OrganizationRole.AGENT)
    requester, _, _ = create_account(
        db_session, OrganizationRole.REQUESTER, organization
    )
    ticket = create_ticket(db_session, organization, requester, assignee=agent)

    response = client.post(
        comments_path(ticket),
        headers=auth_headers(agent, membership),
        json={"content": "Estou verificando."},
    )

    assert response.status_code == 201


@pytest.mark.parametrize("role", [OrganizationRole.AGENT, OrganizationRole.REQUESTER])
def test_operational_user_is_blocked_from_unrelated_ticket(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    actor, organization, membership = create_account(db_session, role)
    requester, _, _ = create_account(
        db_session, OrganizationRole.REQUESTER, organization
    )
    ticket = create_ticket(db_session, organization, requester)

    response = client.post(
        comments_path(ticket),
        headers=auth_headers(actor, membership),
        json={"content": "Sem acesso"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_requester_comments_on_own_ticket(
    client: TestClient, db_session: Session
) -> None:
    requester, organization, membership = create_account(
        db_session, OrganizationRole.REQUESTER
    )
    ticket = create_ticket(db_session, organization, requester)

    response = client.post(
        comments_path(ticket),
        headers=auth_headers(requester, membership),
        json={"content": "Informação adicional"},
    )

    assert response.status_code == 201


def test_external_organization_ticket_is_hidden(
    client: TestClient, db_session: Session
) -> None:
    admin, _, membership = create_account(db_session, OrganizationRole.ADMIN)
    external, external_org, _ = create_account(db_session, OrganizationRole.ADMIN)
    ticket = create_ticket(db_session, external_org, external)

    response = client.get(
        comments_path(ticket), headers=auth_headers(admin, membership)
    )

    assert response.status_code == 404


@pytest.mark.parametrize("content", ["", "   ", "x" * 5001])
def test_invalid_content_is_rejected(
    content: str, client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    ticket = create_ticket(db_session, organization, admin)

    response = client.post(
        comments_path(ticket),
        headers=auth_headers(admin, membership),
        json={"content": content},
    )

    assert response.status_code == 422


def test_comment_is_trimmed_and_response_does_not_expose_hash(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    ticket = create_ticket(db_session, organization, admin)

    response = client.post(
        comments_path(ticket),
        headers=auth_headers(admin, membership),
        json={"content": "  Mantem   espacos internos.  "},
    )

    assert response.status_code == 201
    assert response.json()["content"] == "Mantem   espacos internos."
    assert "hash" not in response.text.lower()
    assert "password" not in response.text.lower()


def test_cancelled_ticket_rejects_comment(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    ticket = create_ticket(
        db_session, organization, admin, status=TicketStatus.CANCELLED
    )

    response = client.post(
        comments_path(ticket),
        headers=auth_headers(admin, membership),
        json={"content": "Não permitido"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cancelled_ticket_comment"


def test_completed_ticket_accepts_comment(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    ticket = create_ticket(
        db_session, organization, admin, status=TicketStatus.COMPLETED
    )

    response = client.post(
        comments_path(ticket),
        headers=auth_headers(admin, membership),
        json={"content": "Complemento pos-conclusao"},
    )

    assert response.status_code == 201


def test_empty_comment_listing_returns_empty_list(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    ticket = create_ticket(db_session, organization, admin)

    response = client.get(
        comments_path(ticket), headers=auth_headers(admin, membership)
    )

    assert response.status_code == 200
    assert response.json() == []


def test_multiple_comments_are_listed_chronologically_with_correct_authors(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    manager, _, _ = create_account(db_session, OrganizationRole.MANAGER, organization)
    ticket = create_ticket(db_session, organization, admin)
    fixed_now = datetime(2026, 7, 15, 15, tzinfo=UTC)
    later = TicketComment(
        ticket=ticket,
        author=admin,
        content="Segundo",
        created_at=fixed_now,
    )
    earlier = TicketComment(
        ticket=ticket,
        author=manager,
        content="Primeiro",
        created_at=fixed_now - timedelta(minutes=1),
    )
    db_session.add_all([later, earlier])
    db_session.commit()

    response = client.get(
        comments_path(ticket), headers=auth_headers(admin, membership)
    )

    assert response.status_code == 200
    assert [item["content"] for item in response.json()] == ["Primeiro", "Segundo"]
    assert response.json()[0]["author"]["id"] == str(manager.id)
    assert response.json()[1]["author"]["id"] == str(admin.id)
