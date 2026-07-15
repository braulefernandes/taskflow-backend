import uuid

import pytest

from app.api.deps import (
    AuthContext,
    require_admin,
    require_admin_or_manager,
    require_authenticated_user,
)
from app.core.authorization import (
    ensure_active_membership,
    ensure_organization_access,
)
from app.core.exceptions import AppException
from app.models import Organization, OrganizationMember, OrganizationRole, User


def make_context(
    role: OrganizationRole, *, membership_active: bool = True
) -> AuthContext:
    user = User(
        id=uuid.uuid4(),
        name="Usuario",
        email=f"{uuid.uuid4()}@example.com",
        password_hash="hash",
        is_active=True,
    )
    organization = Organization(
        id=uuid.uuid4(),
        name="Organizacao",
        slug=f"org-{uuid.uuid4()}",
    )
    membership = OrganizationMember(
        id=uuid.uuid4(),
        organization_id=organization.id,
        user_id=user.id,
        user=user,
        organization=organization,
        role=role,
        is_active=membership_active,
    )
    return AuthContext(user=user, organization=organization, membership=membership)


def assert_access_error(
    exception: pytest.ExceptionInfo[AppException],
    *,
    status_code: int,
    code: str,
    message: str,
) -> None:
    assert exception.value.status_code == status_code
    assert exception.value.code == code
    assert exception.value.message == message


def test_authenticated_dependency_preserves_typed_context() -> None:
    context = make_context(OrganizationRole.MANAGER)

    result = require_authenticated_user(context)

    assert result is context
    assert result.organization.id == result.membership.organization_id
    assert result.membership.role is OrganizationRole.MANAGER


def test_admin_is_authorized_by_admin_dependency() -> None:
    context = make_context(OrganizationRole.ADMIN)

    assert require_admin(context) is context


def test_manager_is_authorized_only_by_admin_or_manager_dependency() -> None:
    context = make_context(OrganizationRole.MANAGER)

    assert require_admin_or_manager(context) is context
    with pytest.raises(AppException) as exception:
        require_admin(context)

    assert_access_error(
        exception,
        status_code=403,
        code="insufficient_role",
        message="Papel insuficiente.",
    )


@pytest.mark.parametrize("role", [OrganizationRole.AGENT, OrganizationRole.REQUESTER])
def test_operational_roles_are_denied_by_privileged_dependencies(
    role: OrganizationRole,
) -> None:
    context = make_context(role)

    with pytest.raises(AppException) as exception:
        require_admin_or_manager(context)

    assert_access_error(
        exception,
        status_code=403,
        code="insufficient_role",
        message="Papel insuficiente.",
    )


def test_inactive_membership_is_rejected_consistently() -> None:
    context = make_context(OrganizationRole.ADMIN, membership_active=False)

    with pytest.raises(AppException) as exception:
        ensure_active_membership(context.membership)

    assert_access_error(
        exception,
        status_code=403,
        code="membership_inactive",
        message="Membership inativo.",
    )


def test_resource_from_current_organization_is_allowed() -> None:
    context = make_context(OrganizationRole.ADMIN)

    ensure_organization_access(context.organization.id, context)


def test_cross_organization_resource_is_hidden() -> None:
    context = make_context(OrganizationRole.ADMIN)

    with pytest.raises(AppException) as exception:
        ensure_organization_access(uuid.uuid4(), context)

    assert_access_error(
        exception,
        status_code=404,
        code="resource_not_found",
        message="Recurso nao encontrado.",
    )
