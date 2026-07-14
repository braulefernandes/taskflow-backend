from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash, verify_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Organization,
    OrganizationMember,
    OrganizationRole,
    PasswordResetToken,
    User,
)
from app.schemas.password_reset import ForgotPasswordRequest, ResetPasswordRequest
from app.services import password_reset as password_reset_module
from app.services.email import DevelopmentEmailSender, get_email_sender
from app.services.password_reset import (
    FORGOT_PASSWORD_MESSAGE,
    PasswordResetService,
    hash_reset_token,
)


class FakeEmailSender:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def send_password_reset(
        self,
        *,
        to_email: str,
        reset_url: str,
        expires_minutes: int,
    ) -> None:
        self.messages.append(
            {
                "to_email": to_email,
                "reset_url": reset_url,
                "expires_minutes": expires_minutes,
            }
        )

    def last_token(self) -> str:
        reset_url = str(self.messages[-1]["reset_url"])
        return parse_qs(urlparse(reset_url).query)["token"][0]


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
def fake_email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def client(
    db_session: Session,
    fake_email_sender: FakeEmailSender,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_email_sender] = lambda: fake_email_sender
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_account(
    db_session: Session,
    *,
    email: str = "ana@example.com",
    password: str = "Senha123",
    is_active: bool = True,
) -> tuple[User, OrganizationMember]:
    unique = uuid.uuid4()
    user = User(
        name="Ana Silva",
        email=email,
        password_hash=get_password_hash(password),
        is_active=is_active,
    )
    organization = Organization(name="Organizacao", slug=f"org-{unique}")
    membership = OrganizationMember(
        user=user,
        organization=organization,
        role=OrganizationRole.ADMIN,
        is_active=True,
    )
    db_session.add_all([user, organization, membership])
    db_session.commit()
    return user, membership


def create_reset_token(
    db_session: Session,
    user: User,
    *,
    plain_token: str = "token-seguro-de-teste",
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
) -> PasswordResetToken:
    token = PasswordResetToken(
        user=user,
        token_hash=hash_reset_token(plain_token),
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=30),
        used_at=used_at,
    )
    db_session.add(token)
    db_session.commit()
    return token


def forgot_password(client: TestClient, email: str):
    return client.post("/api/v1/auth/forgot-password", json={"email": email})


def reset_password(client: TestClient, token: str, new_password: str = "NovaSenha123"):
    return client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )


def test_existing_email_gets_generic_response_and_fake_email(
    client: TestClient,
    db_session: Session,
    fake_email_sender: FakeEmailSender,
) -> None:
    create_account(db_session)

    response = forgot_password(client, " ANA@Example.COM ")

    assert response.status_code == 200
    assert response.json() == {"message": FORGOT_PASSWORD_MESSAGE}
    assert len(fake_email_sender.messages) == 1
    assert fake_email_sender.messages[0]["to_email"] == "ana@example.com"
    assert "/redefinir-senha?token=" in str(fake_email_sender.messages[0]["reset_url"])


def test_unknown_email_has_identical_response_without_email(
    client: TestClient,
    db_session: Session,
    fake_email_sender: FakeEmailSender,
) -> None:
    create_account(db_session)

    existing = forgot_password(client, "ana@example.com")
    fake_email_sender.messages.clear()
    unknown = forgot_password(client, "ninguem@example.com")

    assert unknown.status_code == existing.status_code == 200
    assert unknown.json() == existing.json()
    assert fake_email_sender.messages == []


def test_only_token_hash_is_persisted(
    client: TestClient,
    db_session: Session,
    fake_email_sender: FakeEmailSender,
) -> None:
    create_account(db_session)

    response = forgot_password(client, "ana@example.com")
    plain_token = fake_email_sender.last_token()
    stored = db_session.scalar(select(PasswordResetToken))

    assert response.status_code == 200
    assert stored is not None
    assert stored.token_hash == hash_reset_token(plain_token)
    assert stored.token_hash != plain_token
    assert plain_token not in stored.token_hash
    assert plain_token not in response.text


def test_expired_token_is_rejected(client: TestClient, db_session: Session) -> None:
    user, _membership = create_account(db_session)
    create_reset_token(
        db_session,
        user,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    response = reset_password(client, "token-seguro-de-teste")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_token"


def test_invalid_token_is_rejected(client: TestClient, db_session: Session) -> None:
    create_account(db_session)

    response = reset_password(client, "token-que-nao-existe")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_token"


def test_used_token_is_rejected(client: TestClient, db_session: Session) -> None:
    user, _membership = create_account(db_session)
    create_reset_token(db_session, user, used_at=datetime.now(UTC))

    response = reset_password(client, "token-seguro-de-teste")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_token"


def test_valid_reset_updates_password_and_marks_token_used(
    client: TestClient,
    db_session: Session,
) -> None:
    user, _membership = create_account(db_session)
    token = create_reset_token(db_session, user)

    response = reset_password(client, "token-seguro-de-teste")

    assert response.status_code == 200
    assert response.json() == {"message": "Senha redefinida com sucesso."}
    assert token.used_at is not None
    assert verify_password("NovaSenha123", user.password_hash)


def test_new_password_allows_login_and_old_password_stops_working(
    client: TestClient,
    db_session: Session,
) -> None:
    user, _membership = create_account(db_session, password="SenhaAntiga123")
    create_reset_token(db_session, user)
    reset = reset_password(client, "token-seguro-de-teste", "SenhaNova123")

    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "SenhaAntiga123"},
    )
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "SenhaNova123"},
    )

    assert reset.status_code == 200
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_reset_token_cannot_be_reused(client: TestClient, db_session: Session) -> None:
    user, _membership = create_account(db_session)
    create_reset_token(db_session, user)

    first = reset_password(client, "token-seguro-de-teste")
    second = reset_password(client, "token-seguro-de-teste", "OutraSenha123")

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_reset_token"


def test_inactive_user_does_not_receive_email_or_reset_password(
    client: TestClient,
    db_session: Session,
    fake_email_sender: FakeEmailSender,
) -> None:
    user, _membership = create_account(db_session, is_active=False)
    forgot = forgot_password(client, user.email)
    token = create_reset_token(db_session, user)
    original_hash = user.password_hash

    reset = reset_password(client, "token-seguro-de-teste")

    assert forgot.status_code == 200
    assert forgot.json() == {"message": FORGOT_PASSWORD_MESSAGE}
    assert fake_email_sender.messages == []
    assert reset.status_code == 400
    assert token.used_at is None
    assert user.password_hash == original_hash


def test_reset_rolls_back_password_and_token_on_failure(
    db_session: Session,
    fake_email_sender: FakeEmailSender,
    monkeypatch,
) -> None:
    user, _membership = create_account(db_session)
    token = create_reset_token(db_session, user)
    original_hash = user.password_hash

    def fail_hash(_password: str) -> str:
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(password_reset_module, "get_password_hash", fail_hash)
    service = PasswordResetService(db_session, fake_email_sender)

    with pytest.raises(RuntimeError, match="simulated failure"):
        service.reset_password(
            ResetPasswordRequest(
                token="token-seguro-de-teste",
                new_password="NovaSenha123",
            )
        )

    db_session.refresh(user)
    db_session.refresh(token)
    assert user.password_hash == original_hash
    assert token.used_at is None


def test_fake_adapter_receives_configured_expiration(
    client: TestClient,
    db_session: Session,
    fake_email_sender: FakeEmailSender,
    monkeypatch,
) -> None:
    create_account(db_session)
    monkeypatch.setattr(
        password_reset_module.settings,
        "password_reset_token_expire_minutes",
        7,
    )

    response = forgot_password(client, "ana@example.com")
    stored = db_session.scalar(select(PasswordResetToken))

    assert response.status_code == 200
    assert fake_email_sender.messages[0]["expires_minutes"] == 7
    assert stored is not None
    remaining = stored.expires_at.replace(tzinfo=UTC) - datetime.now(UTC)
    assert timedelta(minutes=6, seconds=50) < remaining <= timedelta(minutes=7)


def test_plain_token_is_absent_from_response_and_logs(
    client: TestClient,
    db_session: Session,
    fake_email_sender: FakeEmailSender,
    caplog,
) -> None:
    create_account(db_session)

    response = forgot_password(client, "ana@example.com")
    plain_token = fake_email_sender.last_token()

    assert plain_token not in response.text
    assert plain_token not in caplog.text
    assert "password_hash" not in response.text


def test_development_adapter_logs_no_email_url_or_token(caplog) -> None:
    sender = DevelopmentEmailSender()
    token = "segredo-que-nao-pode-aparecer"
    email = "ana@example.com"
    reset_url = f"http://localhost:3000/redefinir-senha?token={token}"

    with caplog.at_level("INFO"):
        sender.send_password_reset(
            to_email=email,
            reset_url=reset_url,
            expires_minutes=30,
        )

    assert "suppressed by development adapter" in caplog.text
    assert token not in caplog.text
    assert reset_url not in caplog.text
    assert email not in caplog.text


def test_email_adapter_failure_rolls_back_token_and_keeps_generic_response(
    db_session: Session,
    caplog,
) -> None:
    create_account(db_session)

    class FailingEmailSender:
        def send_password_reset(self, **_kwargs) -> None:
            raise RuntimeError("sensitive provider detail")

    service = PasswordResetService(db_session, FailingEmailSender())
    with caplog.at_level("ERROR"):
        message = service.request_reset(ForgotPasswordRequest(email="ana@example.com"))

    assert message == FORGOT_PASSWORD_MESSAGE
    assert db_session.scalar(select(PasswordResetToken)) is None
    assert "sensitive provider detail" not in caplog.text
    assert "ana@example.com" not in caplog.text
