import uuid
from http import HTTPStatus

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.core.exceptions import AppException
from app.core.security import get_password_hash
from app.models import OrganizationMember, OrganizationRole
from app.repositories.members import MemberRepository
from app.schemas.members import (
    MemberCreateRequest,
    MemberRoleUpdateRequest,
    MemberStatusUpdateRequest,
)


class MemberService:
    def __init__(self, db: Session, repository: MemberRepository | None = None) -> None:
        self.db = db
        self.repository = repository or MemberRepository(db)

    def list_members(
        self,
        *,
        context: AuthContext,
        search: str | None,
        role: OrganizationRole | None,
        is_active: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[OrganizationMember], int]:
        return self.repository.list_members(
            organization_id=context.organization.id,
            search=search,
            role=role,
            is_active=is_active,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    def get_member(
        self,
        *,
        context: AuthContext,
        membership_id: uuid.UUID,
    ) -> OrganizationMember:
        membership = self.repository.get_member(
            membership_id=membership_id,
            organization_id=context.organization.id,
        )
        if membership is None:
            raise_member_not_found()
        return membership

    def create_member(
        self,
        *,
        context: AuthContext,
        payload: MemberCreateRequest,
    ) -> OrganizationMember:
        try:
            user = self.repository.get_user_by_email(str(payload.email))
            if user is None:
                user = self.repository.create_user(
                    name=payload.name,
                    email=str(payload.email),
                    password_hash=get_password_hash(payload.temporary_password),
                )
            elif self.repository.membership_exists(
                user_id=user.id,
                organization_id=context.organization.id,
            ):
                raise AppException(
                    "Usuário já pertence a esta organização.",
                    status_code=HTTPStatus.CONFLICT,
                    code="membership_already_exists",
                )

            membership = self.repository.create_membership(
                user=user,
                organization=context.organization,
                role=payload.role,
            )
            self.db.commit()
            self.db.refresh(membership)
            return self.get_member(context=context, membership_id=membership.id)
        except AppException:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise AppException(
                "Não foi possível criar o membro.",
                status_code=HTTPStatus.CONFLICT,
                code="member_creation_conflict",
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise AppException(
                "Não foi possível criar o membro.",
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="member_persistence_error",
            ) from exc

    def update_role(
        self,
        *,
        context: AuthContext,
        membership_id: uuid.UUID,
        payload: MemberRoleUpdateRequest,
    ) -> OrganizationMember:
        membership = self.get_member(context=context, membership_id=membership_id)
        if (
            membership.role == OrganizationRole.ADMIN
            and membership.is_active
            and payload.role != OrganizationRole.ADMIN
        ):
            self._ensure_another_active_admin(context)

        membership.role = payload.role
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def update_status(
        self,
        *,
        context: AuthContext,
        membership_id: uuid.UUID,
        payload: MemberStatusUpdateRequest,
    ) -> OrganizationMember:
        membership = self.get_member(context=context, membership_id=membership_id)
        if (
            membership.role == OrganizationRole.ADMIN
            and membership.is_active
            and not payload.is_active
        ):
            self._ensure_another_active_admin(context)

        membership.is_active = payload.is_active
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def _ensure_another_active_admin(self, context: AuthContext) -> None:
        if self.repository.count_active_admins_for_update(context.organization.id) <= 1:
            self.db.rollback()
            raise AppException(
                "A organização deve manter ao menos um administrador ativo.",
                status_code=HTTPStatus.CONFLICT,
                code="last_active_admin",
            )


def raise_member_not_found() -> None:
    raise AppException(
        "Recurso não encontrado.",
        status_code=HTTPStatus.NOT_FOUND,
        code="resource_not_found",
    )
