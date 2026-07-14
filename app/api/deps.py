import uuid
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.authorization import ensure_active_membership, ensure_role
from app.core.exceptions import AppException
from app.core.jwt import InvalidTokenError, TokenExpiredError, decode_access_token
from app.db.session import get_db
from app.models import Organization, OrganizationMember, OrganizationRole, User
from app.repositories.auth import AuthRepository


@dataclass(frozen=True)
class AuthContext:
    user: User
    organization: Organization
    membership: OrganizationMember


def get_current_auth_context(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthContext:
    token = extract_bearer_token(authorization)
    try:
        payload = decode_access_token(token)
    except (InvalidTokenError, TokenExpiredError):
        raise_authentication_error()

    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError, TypeError):
        raise_authentication_error()

    organization_id = None
    if payload.get("org") is not None:
        try:
            organization_id = uuid.UUID(str(payload["org"]))
        except (ValueError, TypeError):
            raise_authentication_error()

    repository = AuthRepository(db)
    user = repository.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise_authentication_error()

    membership = repository.get_membership_for_user(user, organization_id)
    if membership is None or membership.organization is None:
        raise_authentication_error()

    ensure_active_membership(membership)

    return AuthContext(
        user=user,
        organization=membership.organization,
        membership=membership,
    )


def require_authenticated_user(
    context: AuthContext = Depends(get_current_auth_context),
) -> AuthContext:
    return context


def require_roles(
    *allowed_roles: OrganizationRole,
) -> Callable[[AuthContext], AuthContext]:
    def role_dependency(
        context: AuthContext = Depends(require_authenticated_user),
    ) -> AuthContext:
        ensure_role(context.membership, allowed_roles)
        return context

    return role_dependency


require_admin = require_roles(OrganizationRole.ADMIN)
require_admin_or_manager = require_roles(
    OrganizationRole.ADMIN,
    OrganizationRole.MANAGER,
)


def extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise_authentication_error()

    scheme, separator, token = authorization.partition(" ")
    if separator == "" or scheme.lower() != "bearer" or not token.strip():
        raise_authentication_error()

    return token.strip()


def raise_authentication_error() -> None:
    raise AppException(
        "Nao autenticado.",
        status_code=HTTPStatus.UNAUTHORIZED,
        code="not_authenticated",
    )
