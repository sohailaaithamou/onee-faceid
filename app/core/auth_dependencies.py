from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import UserAccount


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
SessionDependency = Annotated[Session, Depends(get_db)]
TokenDependency = Annotated[str, Depends(oauth2_scheme)]


def _credentials_error(detail: str = "Authentification requise.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_account(
    db: SessionDependency,
    token: TokenDependency,
) -> UserAccount:
    try:
        payload = decode_access_token(token)
        account_id = int(payload["sub"])
    except (ValueError, TypeError, KeyError):
        raise _credentials_error("Jeton d'accès invalide ou expiré.")

    statement = (
        select(UserAccount)
        .options(selectinload(UserAccount.person))
        .where(UserAccount.id == account_id)
    )
    account = db.scalar(statement)

    if account is None:
        raise _credentials_error("Compte utilisateur introuvable.")

    if not account.active:
        raise _credentials_error("Ce compte utilisateur est désactivé.")

    return account


CurrentAccount = Annotated[UserAccount, Depends(get_current_account)]


def require_roles(*allowed_roles: str) -> Callable[..., UserAccount]:
    normalized_roles = {role.upper() for role in allowed_roles}

    def dependency(
        account: CurrentAccount,
    ) -> UserAccount:
        if account.role.upper() not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas l'autorisation d'effectuer cette opération.",
            )
        return account

    return dependency
