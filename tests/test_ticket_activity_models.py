import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import (
    Category,
    Organization,
    Ticket,
    TicketComment,
    TicketHistory,
    TicketHistoryAction,
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


def activity_graph() -> tuple[Ticket, User]:
    organization = Organization(name="Acme", slug=f"acme-{uuid.uuid4()}")
    category = Category(
        organization=organization, name="Support", normalized_name="support"
    )
    author = User(
        name="Ana", email=f"ana-{uuid.uuid4()}@example.com", password_hash="hash"
    )
    ticket = Ticket(
        organization=organization,
        category=category,
        requester=author,
        title="Access required",
        description="Grant access to the finance system.",
    )
    return ticket, author


def test_comment_creation_and_relationships(db_session: Session) -> None:
    ticket, author = activity_graph()
    comment = TicketComment(ticket=ticket, author=author, content="Work started.")
    db_session.add(comment)
    db_session.commit()

    assert comment.id is not None
    assert comment.ticket is ticket
    assert comment.author is author
    assert comment in ticket.comments
    assert comment in author.ticket_comments
    assert isinstance(comment.created_at, datetime)
    assert isinstance(comment.updated_at, datetime)


@pytest.mark.parametrize("content", [None, "", "   ", "x" * 5001])
def test_comment_content_is_required_and_bounded(
    db_session: Session, content: str | None
) -> None:
    ticket, author = activity_graph()
    db_session.add(TicketComment(ticket=ticket, author=author, content=content))  # type: ignore[arg-type]

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_history_creation_optional_values_and_relationships(
    db_session: Session,
) -> None:
    ticket, author = activity_graph()
    history = TicketHistory(
        ticket=ticket,
        user=author,
        action=TicketHistoryAction.CREATED,
    )
    db_session.add(history)
    db_session.commit()

    assert history.id is not None
    assert history.field_name is None
    assert history.old_value is None
    assert history.new_value is None
    assert history.ticket is ticket
    assert history.user is author
    assert history in ticket.history
    assert history in author.ticket_history
    assert isinstance(history.created_at, datetime)


def test_history_action_is_required(db_session: Session) -> None:
    ticket, author = activity_graph()
    db_session.add(TicketHistory(ticket=ticket, user=author, action=None))  # type: ignore[arg-type]

    with pytest.raises((IntegrityError, StatementError)):
        db_session.commit()


@pytest.mark.parametrize("model", ["comment", "history"])
@pytest.mark.parametrize("missing_relation", ["ticket", "user"])
def test_activity_rejects_missing_ticket_or_user(
    db_session: Session, model: str, missing_relation: str
) -> None:
    ticket, author = activity_graph()
    db_session.add_all([ticket, author])
    db_session.flush()
    ticket_id = uuid.uuid4() if missing_relation == "ticket" else ticket.id
    user_id = uuid.uuid4() if missing_relation == "user" else author.id
    if model == "comment":
        activity = TicketComment(
            ticket_id=ticket_id, author_id=user_id, content="Valid content"
        )
    else:
        activity = TicketHistory(
            ticket_id=ticket_id,
            user_id=user_id,
            action=TicketHistoryAction.CREATED,
        )
    db_session.add(activity)

    with pytest.raises(IntegrityError):
        db_session.commit()
