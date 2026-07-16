from http import HTTPStatus

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.core.exceptions import AppException
from app.models import User
from app.schemas.users import UserProfileUpdateRequest


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def update_own_profile(
        self,
        *,
        context: AuthContext,
        payload: UserProfileUpdateRequest,
    ) -> User:
        user = context.user
        if "name" in payload.model_fields_set:
            assert payload.name is not None
            user.name = payload.name
        if "avatar_url" in payload.model_fields_set:
            user.avatar_url = (
                str(payload.avatar_url) if payload.avatar_url is not None else None
            )

        try:
            self.db.commit()
            self.db.refresh(user)
            return user
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise AppException(
                "Não foi possível atualizar o perfil.",
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="profile_persistence_error",
            ) from exc
