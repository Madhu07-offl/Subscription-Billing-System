from fastapi import APIRouter, status

from app.core import security
from app.core.deps import CurrentUser, DbSession
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ProfileUpdate,
    ResetPasswordRequest,
    SignupRequest,
    UserOut,
)
from app.schemas.common import Message
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


def _auth_response(user) -> AuthResponse:
    token, expires_in = security.create_access_token(user.id, user.role)
    return AuthResponse(token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: DbSession):
    return _auth_response(auth_service.signup(db, body))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: DbSession):
    return _auth_response(auth_service.login(db, body))


@router.post("/forgot-password", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(body: ForgotPasswordRequest, db: DbSession):
    auth_service.forgot_password(db, body.email)
    return Message(message="If that email is registered, a reset link has been sent")


@router.post("/reset-password", response_model=Message)
def reset_password(body: ResetPasswordRequest, db: DbSession):
    auth_service.reset_password(db, body)
    return Message(message="Password has been reset")


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordRequest, db: DbSession, user: CurrentUser):
    auth_service.change_password(db, user, body)
    return Message(message="Password changed")


@router.get("/me", response_model=UserOut)
def get_me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, db: DbSession, user: CurrentUser):
    return auth_service.update_me(db, user, body)
