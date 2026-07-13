from http import HTTPStatus

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import get_password_hash
from app.core.slug import slug_with_suffix, slugify
from app.models import Organization, OrganizationMember, OrganizationRole, User
from app.repositories.auth import AuthRepository
from app.schemas.auth import RegisterRequest

MAX_SLUG_COLLISION_ATTEMPTS = 100


class RegistrationResult:
    def __init__(
        self,
        *,
        user: User,
        organization: Organization,
        membership: OrganizationMember,
    ) -> None:
        self.user = user
        self.organization = organization
        self.membership = membership


class AuthService:
    def __init__(self, db: Session, repository: AuthRepository | None = None) -> None:
        self.db = db
        self.repository = repository or AuthRepository(db)

    def register(self, payload: RegisterRequest) -> RegistrationResult:
        try:
            if self.repository.get_user_by_email(payload.email) is not None:
                raise AppException(
                    "E-mail ja cadastrado.",
                    status_code=HTTPStatus.CONFLICT,
                    code="email_already_registered",
                )

            organization_slug = self._build_unique_slug(payload.organization_name)
            user = self.repository.create_user(
                name=payload.user_name,
                email=payload.email,
                password_hash=get_password_hash(payload.password),
            )
            organization = self.repository.create_organization(
                name=payload.organization_name,
                slug=organization_slug,
            )
            membership = self.repository.create_membership(
                user=user,
                organization=organization,
                role=OrganizationRole.ADMIN,
            )

            self.db.commit()
            self.db.refresh(user)
            self.db.refresh(organization)
            self.db.refresh(membership)

            return RegistrationResult(
                user=user,
                organization=organization,
                membership=membership,
            )
        except AppException:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise AppException(
                "Nao foi possivel concluir o cadastro.",
                status_code=HTTPStatus.CONFLICT,
                code="registration_conflict",
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise AppException(
                "Nao foi possivel concluir o cadastro.",
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="registration_persistence_error",
            ) from exc
        except Exception:
            self.db.rollback()
            raise

    def _build_unique_slug(self, organization_name: str) -> str:
        base_slug = slugify(organization_name)
        for attempt in range(1, MAX_SLUG_COLLISION_ATTEMPTS + 1):
            candidate = (
                base_slug
                if attempt == 1
                else slug_with_suffix(base_slug, attempt)
            )
            if not self.repository.organization_slug_exists(candidate):
                return candidate

        raise AppException(
            "Nao foi possivel gerar um identificador para a organizacao.",
            status_code=HTTPStatus.CONFLICT,
            code="organization_slug_conflict",
        )
