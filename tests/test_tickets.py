import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

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
from app.models import (
    Category,
    Organization,
    OrganizationMember,
    OrganizationRole,
    Ticket,
    TicketPriority,
    TicketStatus,
    User,
)
from app.schemas import tickets as ticket_schemas


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
        name=f"Usuario {role.value}",
        email=f"{unique}@example.com",
        password_hash=get_password_hash("Senha123"),
    )
    organization = organization or Organization(
        name="Organizacao", slug=f"org-{unique}"
    )
    membership = OrganizationMember(
        user=user, organization=organization, role=role, is_active=True
    )
    db.add_all([user, organization, membership])
    db.commit()
    return user, organization, membership


def headers(user: User, membership: OrganizationMember) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        organization_id=str(membership.organization_id),
        role=membership.role.value,
    )
    return {"Authorization": f"Bearer {token}"}


def create_category(
    db: Session, organization: Organization, *, active: bool = True
) -> Category:
    unique = uuid.uuid4()
    category = Category(
        organization=organization,
        name=f"Categoria {unique}",
        normalized_name=str(unique),
        is_active=active,
    )
    db.add(category)
    db.commit()
    return category


def payload(category: Category, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "title": "  Acesso   ao sistema ",
        "description": "  Liberar acesso financeiro. ",
        "category_id": str(category.id),
        "priority": "HIGH",
        "due_date": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
    }
    data.update(overrides)
    return data


def create_ticket(
    db: Session,
    organization: Organization,
    category: Category,
    requester: User,
    *,
    assignee: User | None = None,
    title: str = "Ticket",
    created_at: datetime | None = None,
) -> Ticket:
    ticket = Ticket(
        organization=organization,
        category=category,
        requester=requester,
        assignee=assignee,
        title=title,
        description="Descricao",
        priority=TicketPriority.MEDIUM,
    )
    if created_at is not None:
        ticket.created_at = created_at
    db.add(ticket)
    db.commit()
    return ticket


@pytest.mark.parametrize("role", list(OrganizationRole))
def test_all_roles_can_create_with_session_owned_fields(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    user, organization, membership = create_account(db_session, role)
    category = create_category(db_session, organization)

    response = client.post(
        "/api/v1/tickets", headers=headers(user, membership), json=payload(category)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["organization"]["id"] == str(organization.id)
    assert body["requester"]["id"] == str(user.id)
    assert body["assignee"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["cancelled_at"] is None
    assert body["title"] == "Acesso ao sistema"
    assert "password" not in response.text.lower()
    assert "hash" not in response.text.lower()


def test_creation_rejects_inactive_and_external_categories(
    client: TestClient, db_session: Session
) -> None:
    user, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    inactive = create_category(db_session, organization, active=False)
    _other, other_org, _membership = create_account(db_session, OrganizationRole.ADMIN)
    external = create_category(db_session, other_org)

    inactive_response = client.post(
        "/api/v1/tickets", headers=headers(user, membership), json=payload(inactive)
    )
    external_response = client.post(
        "/api/v1/tickets", headers=headers(user, membership), json=payload(external)
    )

    assert inactive_response.status_code == 400
    assert inactive_response.json()["error"]["code"] == "category_inactive"
    assert external_response.status_code == 404


def test_creation_rejects_past_due_date(
    client: TestClient, db_session: Session
) -> None:
    user, organization, membership = create_account(
        db_session, OrganizationRole.REQUESTER
    )
    category = create_category(db_session, organization)
    response = client.post(
        "/api/v1/tickets",
        headers=headers(user, membership),
        json=payload(
            category, due_date=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        ),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "due_date_in_past"


def test_internal_fields_and_invalid_priority_are_rejected(
    client: TestClient, db_session: Session
) -> None:
    user, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    for forbidden in (
        "organization_id",
        "requester_id",
        "status",
        "assignee_id",
        "started_at",
    ):
        response = client.post(
            "/api/v1/tickets",
            headers=headers(user, membership),
            json=payload(category, **{forbidden: str(uuid.uuid4())}),
        )
        assert response.status_code == 422
    invalid = client.post(
        "/api/v1/tickets",
        headers=headers(user, membership),
        json=payload(category, priority="INVALID"),
    )
    assert invalid.status_code == 422


def test_admin_listing_is_paginated_isolated_and_newest_first(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    old = create_ticket(
        db_session,
        organization,
        category,
        admin,
        title="Antigo",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    new = create_ticket(db_session, organization, category, admin, title="Novo")
    other, other_org, _ = create_account(db_session, OrganizationRole.ADMIN)
    other_category = create_category(db_session, other_org)
    create_ticket(db_session, other_org, other_category, other)

    first = client.get(
        "/api/v1/tickets?page=1&page_size=1", headers=headers(admin, membership)
    )
    second = client.get(
        "/api/v1/tickets?page=2&page_size=1", headers=headers(admin, membership)
    )

    assert first.json()["total"] == 2
    assert first.json()["items"][0]["id"] == str(new.id)
    assert second.json()["items"][0]["id"] == str(old.id)


def test_requester_sees_only_own_tickets(
    client: TestClient, db_session: Session
) -> None:
    requester, organization, membership = create_account(
        db_session, OrganizationRole.REQUESTER
    )
    other, _, _ = create_account(db_session, OrganizationRole.REQUESTER, organization)
    category = create_category(db_session, organization)
    own = create_ticket(db_session, organization, category, requester)
    hidden = create_ticket(db_session, organization, category, other)

    listing = client.get("/api/v1/tickets", headers=headers(requester, membership))
    detail = client.get(
        f"/api/v1/tickets/{hidden.id}", headers=headers(requester, membership)
    )

    assert [item["id"] for item in listing.json()["items"]] == [str(own.id)]
    assert detail.status_code == 404


def test_agent_sees_created_and_assigned_tickets(
    client: TestClient, db_session: Session
) -> None:
    agent, organization, membership = create_account(db_session, OrganizationRole.AGENT)
    other, _, _ = create_account(db_session, OrganizationRole.REQUESTER, organization)
    category = create_category(db_session, organization)
    own = create_ticket(db_session, organization, category, agent)
    assigned = create_ticket(db_session, organization, category, other, assignee=agent)
    create_ticket(db_session, organization, category, other, title="Oculto")

    response = client.get("/api/v1/tickets", headers=headers(agent, membership))
    assert {item["id"] for item in response.json()["items"]} == {
        str(own.id),
        str(assigned.id),
    }


def test_admin_gets_ticket_with_public_relationships(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    response = client.get(
        f"/api/v1/tickets/{ticket.id}", headers=headers(admin, membership)
    )
    assert response.status_code == 200
    assert response.json()["category"]["id"] == str(category.id)
    assert response.json()["requester"]["email"] == admin.email
    assert "password_hash" not in response.text


@pytest.mark.parametrize("role", [OrganizationRole.ADMIN, OrganizationRole.MANAGER])
def test_admin_and_manager_can_edit(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    editor, organization, membership = create_account(db_session, role)
    requester, _, _ = create_account(
        db_session, OrganizationRole.REQUESTER, organization
    )
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, requester)
    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(editor, membership),
        json={"title": "Novo titulo", "priority": "URGENT", "due_date": None},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Novo titulo"
    assert response.json()["priority"] == "URGENT"


def test_requester_edits_own_pending_unassigned_ticket(
    client: TestClient, db_session: Session
) -> None:
    requester, organization, membership = create_account(
        db_session, OrganizationRole.REQUESTER
    )
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, requester)
    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(requester, membership),
        json={"description": "Atualizada"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Atualizada"


def test_agent_cannot_edit_and_requester_cannot_edit_assigned_ticket(
    client: TestClient, db_session: Session
) -> None:
    agent, organization, agent_membership = create_account(
        db_session, OrganizationRole.AGENT
    )
    requester, _, requester_membership = create_account(
        db_session, OrganizationRole.REQUESTER, organization
    )
    category = create_category(db_session, organization)
    ticket = create_ticket(
        db_session, organization, category, requester, assignee=agent
    )
    for user, membership in (
        (agent, agent_membership),
        (requester, requester_membership),
    ):
        response = client.patch(
            f"/api/v1/tickets/{ticket.id}",
            headers=headers(user, membership),
            json={"title": "Negado"},
        )
        assert response.status_code == 403


def test_update_rejects_internal_fields(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    for field, value in (
        ("status", "COMPLETED"),
        ("assignee_id", str(admin.id)),
        ("organization_id", str(organization.id)),
        ("completed_at", None),
    ):
        response = client.patch(
            f"/api/v1/tickets/{ticket.id}",
            headers=headers(admin, membership),
            json={field: value},
        )
        assert response.status_code == 422


def test_ticket_from_another_organization_is_hidden_for_get_and_patch(
    client: TestClient, db_session: Session
) -> None:
    admin, _, membership = create_account(db_session, OrganizationRole.ADMIN)
    other, other_org, _ = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, other_org)
    ticket = create_ticket(db_session, other_org, category, other)
    get_response = client.get(
        f"/api/v1/tickets/{ticket.id}", headers=headers(admin, membership)
    )
    patch_response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(admin, membership),
        json={"title": "Invasao"},
    )
    assert get_response.status_code == 404
    assert patch_response.status_code == 404


@pytest.mark.parametrize("role", [OrganizationRole.ADMIN, OrganizationRole.MANAGER])
def test_admin_and_manager_assign_eligible_member(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    actor, organization, membership = create_account(db_session, role)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, actor)

    response = client.patch(
        f"/api/v1/tickets/{ticket.id}/assignee",
        headers=headers(actor, membership),
        json={"assignee_id": str(agent.id)},
    )

    assert response.status_code == 200
    assert response.json()["assignee"] == {
        "id": str(agent.id),
        "name": agent.name,
        "email": agent.email,
        "avatar_url": None,
    }
    assert response.json()["status"] == "PENDING"
    assert "password" not in response.text.lower()
    assert "hash" not in response.text.lower()


@pytest.mark.parametrize("role", [OrganizationRole.AGENT, OrganizationRole.REQUESTER])
def test_agent_and_requester_cannot_assign(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    actor, organization, membership = create_account(db_session, role)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, actor)

    response = client.patch(
        f"/api/v1/tickets/{ticket.id}/assignee",
        headers=headers(actor, membership),
        json={"assignee_id": str(agent.id)},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_external_and_nonexistent_assignees_are_hidden(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    external, _external_org, _ = create_account(db_session, OrganizationRole.AGENT)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)

    for assignee_id in (external.id, uuid.uuid4()):
        response = client.patch(
            f"/api/v1/tickets/{ticket.id}/assignee",
            headers=headers(admin, membership),
            json={"assignee_id": str(assignee_id)},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"


@pytest.mark.parametrize(
    ("inactive_target", "expected_code"),
    [
        ("membership", "assignee_membership_inactive"),
        ("user", "assignee_user_inactive"),
    ],
)
def test_inactive_membership_or_user_cannot_be_assigned(
    inactive_target: str,
    expected_code: str,
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, agent_membership = create_account(
        db_session, OrganizationRole.AGENT, organization
    )
    if inactive_target == "membership":
        agent_membership.is_active = False
    else:
        agent.is_active = False
    db_session.commit()
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)

    response = client.patch(
        f"/api/v1/tickets/{ticket.id}/assignee",
        headers=headers(admin, membership),
        json={"assignee_id": str(agent.id)},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == expected_code


def test_requester_role_cannot_be_assignee(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    requester, _, _ = create_account(
        db_session, OrganizationRole.REQUESTER, organization
    )
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)

    response = client.patch(
        f"/api/v1/tickets/{ticket.id}/assignee",
        headers=headers(admin, membership),
        json={"assignee_id": str(requester.id)},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "assignee_role_not_allowed"


def test_assignee_can_be_replaced_removed_and_repeated_idempotently(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    first, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    second, _, _ = create_account(db_session, OrganizationRole.MANAGER, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin, assignee=first)
    path = f"/api/v1/tickets/{ticket.id}/assignee"

    changed = client.patch(
        path, headers=headers(admin, membership), json={"assignee_id": str(second.id)}
    )
    repeated = client.patch(
        path, headers=headers(admin, membership), json={"assignee_id": str(second.id)}
    )
    removed = client.patch(
        path, headers=headers(admin, membership), json={"assignee_id": None}
    )

    assert changed.json()["assignee"]["id"] == str(second.id)
    assert repeated.status_code == 200
    assert repeated.json()["assignee"]["id"] == str(second.id)
    assert removed.status_code == 200
    assert removed.json()["assignee"] is None


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (TicketStatus.CANCELLED, "cancelled_ticket_assignment"),
        (TicketStatus.COMPLETED, "completed_ticket_assignment"),
    ],
)
def test_terminal_ticket_rejects_assignment_changes(
    status: TicketStatus,
    code: str,
    client: TestClient,
    db_session: Session,
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    ticket.status = status
    db_session.commit()

    response = client.patch(
        f"/api/v1/tickets/{ticket.id}/assignee",
        headers=headers(admin, membership),
        json={"assignee_id": str(agent.id)},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == code


def test_external_ticket_is_hidden_on_assignment(
    client: TestClient, db_session: Session
) -> None:
    admin, _, membership = create_account(db_session, OrganizationRole.ADMIN)
    other, other_org, _ = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, other_org)
    category = create_category(db_session, other_org)
    ticket = create_ticket(db_session, other_org, category, other)

    response = client.patch(
        f"/api/v1/tickets/{ticket.id}/assignee",
        headers=headers(admin, membership),
        json={"assignee_id": str(agent.id)},
    )
    assert response.status_code == 404


def status_path(ticket: Ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/status"


def test_valid_status_transition_sets_utc_started_at(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin, assignee=agent)

    response = client.patch(
        status_path(ticket),
        headers=headers(admin, membership),
        json={"status": "IN_PROGRESS"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"
    started_at = datetime.fromisoformat(response.json()["started_at"])
    assert started_at.tzinfo is not None
    assert started_at.utcoffset() == timedelta(0)


def test_invalid_status_transition_is_rejected(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin, assignee=agent)

    response = client.patch(
        status_path(ticket),
        headers=headers(admin, membership),
        json={"status": "COMPLETED"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"


def test_started_at_is_not_overwritten_after_later_progress_entry(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin, assignee=agent)
    path = status_path(ticket)

    first = client.patch(
        path, headers=headers(admin, membership), json={"status": "IN_PROGRESS"}
    )
    client.patch(path, headers=headers(admin, membership), json={"status": "WAITING"})
    second = client.patch(
        path, headers=headers(admin, membership), json={"status": "IN_PROGRESS"}
    )
    assert second.json()["started_at"] == first.json()["started_at"]


def test_completion_and_controlled_reopening_manage_completed_at(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin, assignee=agent)
    ticket.status = TicketStatus.IN_PROGRESS
    ticket.started_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    completed = client.patch(
        status_path(ticket),
        headers=headers(admin, membership),
        json={"status": "COMPLETED"},
    )
    reopened = client.patch(
        status_path(ticket),
        headers=headers(admin, membership),
        json={"status": "IN_PROGRESS"},
    )

    assert completed.status_code == 200
    assert completed.json()["completed_at"] is not None
    assert datetime.fromisoformat(
        completed.json()["completed_at"]
    ).utcoffset() == timedelta(0)
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "IN_PROGRESS"
    assert reopened.json()["completed_at"] is None
    assert reopened.json()["cancelled_at"] is None


def test_waiting_can_be_completed(client: TestClient, db_session: Session) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin, assignee=agent)
    ticket.status = TicketStatus.WAITING
    db_session.commit()
    response = client.patch(
        status_path(ticket),
        headers=headers(admin, membership),
        json={"status": "COMPLETED"},
    )
    assert response.status_code == 200


def test_assigned_agent_can_change_status_but_other_agent_cannot(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, _ = create_account(db_session, OrganizationRole.ADMIN)
    assigned, _, assigned_membership = create_account(
        db_session, OrganizationRole.AGENT, organization
    )
    other, _, other_membership = create_account(
        db_session, OrganizationRole.AGENT, organization
    )
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin, assignee=assigned)

    allowed = client.patch(
        status_path(ticket),
        headers=headers(assigned, assigned_membership),
        json={"status": "IN_PROGRESS"},
    )
    denied = client.patch(
        status_path(ticket),
        headers=headers(other, other_membership),
        json={"status": "WAITING"},
    )
    assert allowed.status_code == 200
    assert denied.status_code == 404


def test_agent_who_created_but_is_not_assigned_cannot_change_status(
    client: TestClient, db_session: Session
) -> None:
    agent, organization, membership = create_account(db_session, OrganizationRole.AGENT)
    responsible, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(
        db_session, organization, category, agent, assignee=responsible
    )
    response = client.patch(
        status_path(ticket),
        headers=headers(agent, membership),
        json={"status": "IN_PROGRESS"},
    )
    assert response.status_code == 403


def test_requester_cannot_change_operational_status(
    client: TestClient, db_session: Session
) -> None:
    requester, organization, membership = create_account(
        db_session, OrganizationRole.REQUESTER
    )
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(
        db_session, organization, category, requester, assignee=agent
    )
    response = client.patch(
        status_path(ticket),
        headers=headers(requester, membership),
        json={"status": "IN_PROGRESS"},
    )
    assert response.status_code == 403


def test_operational_status_requires_assignee(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    response = client.patch(
        status_path(ticket),
        headers=headers(admin, membership),
        json={"status": "IN_PROGRESS"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assignee_required_for_status"


def test_admin_changes_priority_and_removes_future_due_date(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    future = (datetime.now(UTC) + timedelta(days=3)).isoformat()

    changed = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(admin, membership),
        json={"priority": "URGENT", "due_date": future},
    )
    removed = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(admin, membership),
        json={"due_date": None},
    )
    assert changed.status_code == 200
    assert changed.json()["priority"] == "URGENT"
    assert changed.json()["due_date"] is not None
    assert removed.json()["due_date"] is None


def test_invalid_priority_and_past_due_date_are_rejected(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    path = f"/api/v1/tickets/{ticket.id}"

    invalid_priority = client.patch(
        path, headers=headers(admin, membership), json={"priority": "CRITICAL"}
    )
    past_due = client.patch(
        path,
        headers=headers(admin, membership),
        json={"due_date": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
    )
    assert invalid_priority.status_code == 422
    assert past_due.status_code == 422
    assert past_due.json()["error"]["code"] == "due_date_in_past"


@pytest.mark.parametrize("role", [OrganizationRole.AGENT, OrganizationRole.REQUESTER])
def test_non_management_roles_cannot_change_priority_or_due_date(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    user, organization, membership = create_account(db_session, role)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, user)
    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(user, membership),
        json={"priority": "LOW"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("status", [TicketStatus.COMPLETED, TicketStatus.CANCELLED])
def test_terminal_ticket_blocks_priority_and_due_date_changes(
    status: TicketStatus, client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    ticket.status = status
    db_session.commit()
    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(admin, membership),
        json={"priority": "HIGH", "due_date": None},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "terminal_ticket_planning_update"


def test_cancelled_ticket_has_no_status_transition(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin, assignee=agent)
    ticket.status = TicketStatus.CANCELLED
    db_session.commit()
    response = client.patch(
        status_path(ticket),
        headers=headers(admin, membership),
        json={"status": "IN_PROGRESS"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"


def cancel_path(ticket: Ticket) -> str:
    return f"/api/v1/tickets/{ticket.id}/cancel"


@pytest.mark.parametrize("role", [OrganizationRole.ADMIN, OrganizationRole.MANAGER])
def test_admin_and_manager_cancel_without_physical_deletion(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    actor, organization, membership = create_account(db_session, role)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, actor)

    response = client.post(cancel_path(ticket), headers=headers(actor, membership))

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    cancelled_at = datetime.fromisoformat(response.json()["cancelled_at"])
    assert cancelled_at.tzinfo is not None
    assert cancelled_at.utcoffset() == timedelta(0)
    persisted = db_session.get(Ticket, ticket.id)
    assert persisted is not None
    assert persisted.status == TicketStatus.CANCELLED


def test_requester_cancels_own_pending_ticket(
    client: TestClient, db_session: Session
) -> None:
    requester, organization, membership = create_account(
        db_session, OrganizationRole.REQUESTER
    )
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, requester)
    response = client.post(cancel_path(ticket), headers=headers(requester, membership))
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_requester_cannot_cancel_in_progress_ticket(
    client: TestClient, db_session: Session
) -> None:
    requester, organization, membership = create_account(
        db_session, OrganizationRole.REQUESTER
    )
    agent, _, _ = create_account(db_session, OrganizationRole.AGENT, organization)
    category = create_category(db_session, organization)
    ticket = create_ticket(
        db_session, organization, category, requester, assignee=agent
    )
    ticket.status = TicketStatus.IN_PROGRESS
    db_session.commit()
    response = client.post(cancel_path(ticket), headers=headers(requester, membership))
    assert response.status_code == 403


def test_agent_cannot_cancel(client: TestClient, db_session: Session) -> None:
    agent, organization, membership = create_account(db_session, OrganizationRole.AGENT)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, agent, assignee=agent)
    response = client.post(cancel_path(ticket), headers=headers(agent, membership))
    assert response.status_code == 403


def test_external_ticket_is_hidden_on_cancellation(
    client: TestClient, db_session: Session
) -> None:
    admin, _, membership = create_account(db_session, OrganizationRole.ADMIN)
    other, other_org, _ = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, other_org)
    ticket = create_ticket(db_session, other_org, category, other)
    response = client.post(cancel_path(ticket), headers=headers(admin, membership))
    assert response.status_code == 404


def test_completed_ticket_cannot_be_cancelled(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    ticket.status = TicketStatus.COMPLETED
    ticket.completed_at = datetime.now(UTC)
    db_session.commit()
    response = client.post(cancel_path(ticket), headers=headers(admin, membership))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "completed_ticket_cancellation"


def test_repeated_cancellation_is_idempotent(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    first = client.post(cancel_path(ticket), headers=headers(admin, membership))
    second = client.post(cancel_path(ticket), headers=headers(admin, membership))
    assert second.status_code == 200
    assert second.json()["cancelled_at"] == first.json()["cancelled_at"]


def test_cancelled_ticket_cannot_be_edited(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    client.post(cancel_path(ticket), headers=headers(admin, membership))
    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(admin, membership),
        json={"title": "Negado"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cancelled_ticket_edit"


def test_completed_ticket_allows_descriptive_edit_but_keeps_terminal_state(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    completed_at = datetime.now(UTC) - timedelta(minutes=10)
    ticket.status = TicketStatus.COMPLETED
    ticket.completed_at = completed_at
    db_session.commit()

    response = client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers(admin, membership),
        json={"title": "Titulo corrigido"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Titulo corrigido"
    assert response.json()["status"] == "COMPLETED"
    assert datetime.fromisoformat(response.json()["completed_at"]) == completed_at


@pytest.mark.parametrize(
    ("status", "due_offset", "expected_overdue"),
    [
        (TicketStatus.PENDING, timedelta(hours=-2), True),
        (TicketStatus.COMPLETED, timedelta(hours=-2), False),
        (TicketStatus.CANCELLED, timedelta(hours=-2), False),
        (TicketStatus.PENDING, timedelta(hours=2), False),
    ],
)
def test_overdue_is_derived_from_due_date_and_status(
    status: TicketStatus,
    due_offset: timedelta,
    expected_overdue: bool,
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    db_session: Session,
) -> None:
    fixed_now = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(ticket_schemas, "utc_now", lambda: fixed_now)
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    ticket.status = status
    ticket.due_date = fixed_now + due_offset
    if status == TicketStatus.COMPLETED:
        ticket.completed_at = fixed_now - timedelta(minutes=30)
    if status == TicketStatus.CANCELLED:
        ticket.cancelled_at = fixed_now - timedelta(minutes=30)
    db_session.commit()

    response = client.get(
        f"/api/v1/tickets/{ticket.id}", headers=headers(admin, membership)
    )
    assert response.json()["is_overdue"] is expected_overdue
    assert response.json()["overdue_seconds"] == (7200 if expected_overdue else 0)


def test_ticket_without_due_date_is_not_overdue(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    response = client.get(
        f"/api/v1/tickets/{ticket.id}", headers=headers(admin, membership)
    )
    assert response.json()["is_overdue"] is False
    assert response.json()["overdue_seconds"] == 0


def test_listing_includes_controlled_overdue_fields(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    db_session: Session,
) -> None:
    fixed_now = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(ticket_schemas, "utc_now", lambda: fixed_now)
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    ticket.due_date = fixed_now - timedelta(minutes=90)
    db_session.commit()
    response = client.get("/api/v1/tickets", headers=headers(admin, membership))
    item = response.json()["items"][0]
    assert item["is_overdue"] is True
    assert item["overdue_seconds"] == 5400


def test_overdue_calculation_accepts_naive_database_datetime(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    db_session: Session,
) -> None:
    fixed_now = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)
    monkeypatch.setattr(ticket_schemas, "utc_now", lambda: fixed_now)
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    category = create_category(db_session, organization)
    ticket = create_ticket(db_session, organization, category, admin)
    ticket.due_date = datetime(2026, 7, 14, 14, 0)
    db_session.commit()
    response = client.get(
        f"/api/v1/tickets/{ticket.id}", headers=headers(admin, membership)
    )
    assert response.status_code == 200
    assert response.json()["overdue_seconds"] == 3600


def test_overdue_fields_are_not_persisted() -> None:
    assert "is_overdue" not in Ticket.__table__.c
    assert "overdue_seconds" not in Ticket.__table__.c
