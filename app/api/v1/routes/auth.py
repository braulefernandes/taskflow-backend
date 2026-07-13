from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_current_auth_context
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
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


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    result = AuthService(db).login(payload)
    return TokenResponse(
        access_token=result.access_token,
        token_type="bearer",
        expires_in=result.expires_in,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(_context: AuthContext = Depends(get_current_auth_context)) -> LogoutResponse:
    return LogoutResponse(
        message="Logout registrado no cliente. Descarte o token localmente.",
        token_revoked=False,
    )


@router.get("/me", response_model=MeResponse)
def me(context: AuthContext = Depends(get_current_auth_context)) -> MeResponse:
    return MeResponse(
        user=context.user,
        organization=context.organization,
        membership=context.membership,
    )
