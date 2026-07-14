from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_authenticated_user
from app.db.session import get_db
from app.schemas.auth import MeUser
from app.schemas.users import UserProfileUpdateRequest
from app.services.users import UserService

router = APIRouter(prefix="/users")


@router.patch("/me", response_model=MeUser)
def update_own_profile(
    payload: UserProfileUpdateRequest,
    context: AuthContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> MeUser:
    user = UserService(db).update_own_profile(context=context, payload=payload)
    return MeUser.model_validate(user)
