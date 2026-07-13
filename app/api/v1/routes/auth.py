from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import RegisterRequest, RegisterResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth")


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=HTTPStatus.CREATED,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    result = AuthService(db).register(payload)
    return RegisterResponse(
        user=result.user,
        organization=result.organization,
        membership=result.membership,
    )
