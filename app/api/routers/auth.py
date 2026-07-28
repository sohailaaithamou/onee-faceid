from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth_dependencies import CurrentAccount
from app.core.security import create_access_token
from app.db.session import get_db
from app.models import UserAccount
from app.schemas.auth import (
    MessageResponse,
    PasswordChangeRequest,
    TokenResponse,
    UserAccountResponse,
)
from app.services.auth_service import authenticate_account, change_own_password


router = APIRouter(prefix="/auth", tags=["Authentication"])
SessionDependency = Annotated[Session, Depends(get_db)]
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


@router.post("/login", response_model=TokenResponse)
def login_route(
    form: LoginForm,
    db: SessionDependency,
) -> TokenResponse:
    account = authenticate_account(db, form.username, form.password)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expires_in = create_access_token(account)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        account=UserAccountResponse.model_validate(account),
    )


@router.get("/me", response_model=UserAccountResponse)
def current_account_route(
    account: CurrentAccount,
) -> UserAccount:
    return account


@router.post("/change-password", response_model=MessageResponse)
def change_password_route(
    payload: PasswordChangeRequest,
    account: CurrentAccount,
    db: SessionDependency,
) -> MessageResponse:
    change_own_password(db, account, payload)
    return MessageResponse(message="Mot de passe modifié avec succès.")
