import uuid
from collections.abc import Collection
from http import HTTPStatus
from typing import Protocol

from app.core.exceptions import AppException
from app.models import Organization, OrganizationMember, OrganizationRole


class OrganizationContext(Protocol):
    organization: Organization


def ensure_active_membership(membership: OrganizationMember) -> None:
    if not membership.is_active:
        raise AppException(
            "Membership inativo.",
            status_code=HTTPStatus.FORBIDDEN,
            code="membership_inactive",
        )


def ensure_role(
    membership: OrganizationMember,
    allowed_roles: Collection[OrganizationRole],
) -> None:
    if membership.role not in allowed_roles:
        raise AppException(
            "Papel insuficiente.",
            status_code=HTTPStatus.FORBIDDEN,
            code="insufficient_role",
        )


def ensure_organization_access(
    resource_organization_id: uuid.UUID,
    context: OrganizationContext,
) -> None:
    if resource_organization_id != context.organization.id:
        raise AppException(
            "Recurso não encontrado.",
            status_code=HTTPStatus.NOT_FOUND,
            code="resource_not_found",
        )
