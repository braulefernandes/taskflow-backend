import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import (
    Category,
    Organization,
    Ticket,
    TicketPriority,
    TicketStatus,
    User,
)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    Base.metadata.drop_all(bind=engine)


def ticket_graph() -> tuple[Ticket, Organization, Category, User]:
    organization = Organization(name="Acme", slug="acme")
    category = Category(
        organization=organization, name="Support", normalized_name="support"
    )
    requester = User(
        name="Ana", email="ana@example.com", password_hash="hashed-password"
    )
    ticket = Ticket(
        organization=organization,
        category=category,
        requester=requester,
        title="Access required",
        description="Grant access to the finance system.",
    )
    return ticket, organization, category, requester


def test_create_ticket_with_defaults_and_relationships(db_session: Session) -> None:
    ticket, organization, category, requester = ticket_graph()
    db_session.add(ticket)
    db_session.commit()

    assert ticket.id is not None
    assert ticket.status is TicketStatus.PENDING
    assert ticket.priority is TicketPriority.MEDIUM
    assert ticket.organization is organization
    assert ticket.category is category
    assert ticket.requester is requester
    assert ticket in organization.tickets
    assert ticket in category.tickets
    assert ticket in requester.requested_tickets


def test_status_and_priority_are_persisted(db_session: Session) -> None:
    ticket, *_ = ticket_graph()
    ticket.status = TicketStatus.IN_PROGRESS
    ticket.priority = TicketPriority.URGENT
    db_session.add(ticket)
    db_session.commit()
    db_session.expire_all()

    persisted = db_session.get(Ticket, ticket.id)
    assert persisted is not None
    assert persisted.status is TicketStatus.IN_PROGRESS
    assert persisted.priority is TicketPriority.URGENT


def test_assignee_and_dates_are_optional(db_session: Session) -> None:
    ticket, *_ = ticket_graph()
    db_session.add(ticket)
    db_session.commit()

    assert ticket.assignee is None
    assert ticket.assignee_id is None
    assert ticket.due_date is None
    assert ticket.started_at is None
    assert ticket.completed_at is None
    assert ticket.cancelled_at is None


def test_assignee_relationship_is_explicit(db_session: Session) -> None:
    ticket, *_ = ticket_graph()
    assignee = User(name="Bob", email="bob@example.com", password_hash="hash")
    ticket.assignee = assignee
    ticket.due_date = datetime.now(UTC) + timedelta(days=1)
    db_session.add(ticket)
    db_session.commit()

    assert ticket.assignee is assignee
    assert ticket in assignee.assigned_tickets
    assert ticket.requester is not assignee


@pytest.mark.parametrize("field", ["status", "priority"])
def test_invalid_enum_is_rejected(db_session: Session, field: str) -> None:
    ticket, *_ = ticket_graph()
    setattr(ticket, field, "INVALID")
    db_session.add(ticket)

    with pytest.raises(StatementError):
        db_session.commit()


@pytest.mark.parametrize(
    "foreign_key", ["organization_id", "category_id", "requester_id"]
)
def test_required_nonexistent_foreign_key_is_rejected(
    db_session: Session, foreign_key: str
) -> None:
    _, organization, category, requester = ticket_graph()
    db_session.add_all([organization, category, requester])
    db_session.commit()
    ticket = Ticket(
        organization_id=organization.id,
        category_id=category.id,
        requester_id=requester.id,
        title="Access required",
        description="Grant access to the finance system.",
    )
    setattr(ticket, foreign_key, uuid.uuid4())
    db_session.add(ticket)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_nonexistent_assignee_is_rejected(db_session: Session) -> None:
    ticket, *_ = ticket_graph()
    ticket.assignee_id = uuid.uuid4()
    db_session.add(ticket)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_required_fields_are_not_nullable() -> None:
    required = {
        "organization_id",
        "title",
        "description",
        "status",
        "priority",
        "category_id",
        "requester_id",
        "created_at",
        "updated_at",
    }
    assert all(not Ticket.__table__.c[name].nullable for name in required)


def test_overdue_is_not_a_persisted_status() -> None:
    assert "OVERDUE" not in TicketStatus.__members__
    assert {status.value for status in TicketStatus} == {
        "PENDING",
        "IN_PROGRESS",
        "WAITING",
        "COMPLETED",
        "CANCELLED",
    }
