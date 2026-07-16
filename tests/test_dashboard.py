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
    TicketPriority,
    TicketStatus,
    User,
)
from app.services import dashboard as dashboard_services


FIXED_NOW = datetime(2026, 7, 15, 15, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_dashboard_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dashboard_services, "utc_now", lambda: FIXED_NOW)


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
        password_hash="hash",
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


def headers(user: User, membership: OrganizationMember) -> dict[str, str]:
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
    status: TicketStatus = TicketStatus.PENDING,
    priority: TicketPriority = TicketPriority.MEDIUM,
    created_at: datetime | None = None,
    due_date: datetime | None = None,
    completed_at: datetime | None = None,
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
        title=f"Ticket {unique}",
        description="Descrição",
        status=status,
        priority=priority,
        due_date=due_date,
        completed_at=completed_at,
    )
    if created_at is not None:
        ticket.created_at = created_at
    db.add(ticket)
    db.commit()
    return ticket


def test_empty_summary_returns_zeros_and_null_average(
    client: TestClient, db_session: Session
) -> None:
    admin, _, membership = create_account(db_session, OrganizationRole.ADMIN)
    response = client.get(
        "/api/v1/dashboard/summary", headers=headers(admin, membership)
    )
    assert response.status_code == 200
    assert response.json() == {
        "total": 0,
        "pending": 0,
        "in_progress": 0,
        "waiting": 0,
        "completed": 0,
        "cancelled": 0,
        "overdue": 0,
        "average_resolution_hours": None,
    }


def test_summary_counts_all_statuses_overdue_and_average_resolution(
    client: TestClient, db_session: Session
) -> None:
    manager, organization, membership = create_account(
        db_session, OrganizationRole.MANAGER
    )
    now = FIXED_NOW
    for status in TicketStatus:
        create_ticket(
            db_session,
            organization,
            manager,
            status=status,
            created_at=now - timedelta(hours=4),
            completed_at=now if status == TicketStatus.COMPLETED else None,
            due_date=(
                now - timedelta(hours=2)
                if status
                in {
                    TicketStatus.PENDING,
                    TicketStatus.COMPLETED,
                    TicketStatus.CANCELLED,
                }
                else now + timedelta(hours=2)
            ),
        )

    response = client.get(
        "/api/v1/dashboard/summary", headers=headers(manager, membership)
    )
    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 5
    assert body["pending"] == 1
    assert body["in_progress"] == 1
    assert body["waiting"] == 1
    assert body["completed"] == 1
    assert body["cancelled"] == 1
    assert body["overdue"] == 1
    assert body["average_resolution_hours"] == 4.0


def test_average_resolution_uses_only_completed_tickets_and_utc(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    created_at = datetime(2026, 7, 15, 8, tzinfo=UTC)
    create_ticket(
        db_session,
        organization,
        admin,
        status=TicketStatus.COMPLETED,
        created_at=created_at,
        completed_at=datetime(2026, 7, 15, 10, tzinfo=UTC),
    )
    create_ticket(
        db_session,
        organization,
        admin,
        status=TicketStatus.COMPLETED,
        created_at=created_at,
        completed_at=datetime(2026, 7, 15, 14, tzinfo=UTC),
    )
    create_ticket(db_session, organization, admin, status=TicketStatus.IN_PROGRESS)

    body = client.get(
        "/api/v1/dashboard/summary", headers=headers(admin, membership)
    ).json()

    assert body["average_resolution_hours"] == 4.0


def test_distributions_return_every_enum_including_zeros(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    create_ticket(
        db_session,
        organization,
        admin,
        status=TicketStatus.PENDING,
        priority=TicketPriority.HIGH,
    )

    statuses = client.get(
        "/api/v1/dashboard/status-distribution", headers=headers(admin, membership)
    ).json()
    priorities = client.get(
        "/api/v1/dashboard/priority-distribution", headers=headers(admin, membership)
    ).json()

    assert {item["status"]: item["count"] for item in statuses} == {
        status.value: (1 if status == TicketStatus.PENDING else 0)
        for status in TicketStatus
    }
    assert {item["priority"]: item["count"] for item in priorities} == {
        priority.value: (1 if priority == TicketPriority.HIGH else 0)
        for priority in TicketPriority
    }


def test_recent_tickets_are_descending_and_limited(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    tickets = [
        create_ticket(
            db_session,
            organization,
            admin,
            created_at=datetime(2026, 7, day, tzinfo=UTC),
        )
        for day in (10, 11, 12)
    ]

    response = client.get(
        "/api/v1/dashboard/recent?limit=2", headers=headers(admin, membership)
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        str(tickets[2].id),
        str(tickets[1].id),
    ]
    assert "description" not in response.json()[0]


def test_dashboard_list_limits_are_validated(
    client: TestClient, db_session: Session
) -> None:
    admin, _, membership = create_account(db_session, OrganizationRole.ADMIN)
    for endpoint in ("recent", "overdue"):
        response = client.get(
            f"/api/v1/dashboard/{endpoint}?limit=51",
            headers=headers(admin, membership),
        )
        assert response.status_code == 422


def test_largest_overdue_are_ordered_and_terminal_tickets_are_excluded(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    now = FIXED_NOW
    largest = create_ticket(
        db_session, organization, admin, due_date=now - timedelta(hours=5)
    )
    smaller = create_ticket(
        db_session, organization, admin, due_date=now - timedelta(hours=2)
    )
    create_ticket(
        db_session,
        organization,
        admin,
        status=TicketStatus.COMPLETED,
        due_date=now - timedelta(hours=10),
        completed_at=now,
    )
    create_ticket(
        db_session,
        organization,
        admin,
        status=TicketStatus.CANCELLED,
        due_date=now - timedelta(hours=10),
    )

    response = client.get(
        "/api/v1/dashboard/overdue", headers=headers(admin, membership)
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        str(largest.id),
        str(smaller.id),
    ]
    assert response.json()[0]["overdue_seconds"] > response.json()[1]["overdue_seconds"]
    assert response.json()[0]["due_date"] is not None


def test_dashboard_is_isolated_by_organization(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    external, external_org, _ = create_account(db_session, OrganizationRole.ADMIN)
    own = create_ticket(db_session, organization, admin)
    create_ticket(db_session, external_org, external)

    summary = client.get(
        "/api/v1/dashboard/summary", headers=headers(admin, membership)
    ).json()
    recent = client.get(
        "/api/v1/dashboard/recent", headers=headers(admin, membership)
    ).json()

    assert summary["total"] == 1
    assert [item["id"] for item in recent] == [str(own.id)]


@pytest.mark.parametrize("role", [OrganizationRole.AGENT, OrganizationRole.REQUESTER])
def test_operational_roles_cannot_access_management_dashboard(
    role: OrganizationRole, client: TestClient, db_session: Session
) -> None:
    user, _, membership = create_account(db_session, role)
    response = client.get(
        "/api/v1/dashboard/summary", headers=headers(user, membership)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_recent_endpoint_has_constant_query_count_without_n_plus_one(
    client: TestClient, db_session: Session
) -> None:
    admin, organization, membership = create_account(db_session, OrganizationRole.ADMIN)
    for _ in range(10):
        create_ticket(db_session, organization, admin)
    db_session.expire_all()
    statements: list[str] = []

    def count_queries(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", count_queries)
    try:
        response = client.get(
            "/api/v1/dashboard/recent?limit=10", headers=headers(admin, membership)
        )
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", count_queries)

    assert response.status_code == 200
    assert len(response.json()) == 10
    assert len(statements) <= 4
