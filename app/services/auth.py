from http import HTTPStatus

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.jwt import create_access_token
from app.core.security import get_password_hash
from app.core.security import verify_password
from app.core.slug import slug_with_suffix, slugify
from app.models import Organization, OrganizationMember, OrganizationRole, User
from app.repositories.auth import AuthRepository
from app.schemas.auth import LoginRequest, RegisterRequest

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


class LoginResult:
    def __init__(self, *, access_token: str, expires_in: int) -> None:
        self.access_token = access_token
        self.expires_in = expires_in


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

    def login(self, payload: LoginRequest) -> LoginResult:
        user = self.repository.get_user_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise_invalid_credentials()

        if not user.is_active:
            raise_invalid_credentials()

        membership = self.repository.get_active_membership_for_user(user)
        if membership is None:
            raise_invalid_credentials()

        expires_in = settings.access_token_expire_minutes * 60
        token = create_access_token(
            subject=str(user.id),
            organization_id=str(membership.organization_id),
            role=membership.role.value,
        )
        return LoginResult(access_token=token, expires_in=expires_in)

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


def raise_invalid_credentials() -> None:
    raise AppException(
        "Credenciais invalidas.",
        status_code=HTTPStatus.UNAUTHORIZED,
        code="invalid_credentials",
    )
