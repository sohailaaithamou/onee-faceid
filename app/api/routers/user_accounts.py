from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth_dependencies import require_roles
from app.db.session import get_db
from app.models import UserAccount
from app.schemas.auth import (
    PasswordResetRequest,
    UserAccountCreate,
    UserAccountResponse,
    UserAccountUpdate,
    UserRole,
)
from app.services.auth_service import (
    create_user_account,
    get_account_or_404,
    list_user_accounts,
    reset_account_password,
    update_user_account,
)


router = APIRouter(prefix="/user-accounts", tags=["User accounts"])
SessionDependency = Annotated[Session, Depends(get_db)]
AdminAccount = Annotated[UserAccount, Depends(require_roles("ADMIN"))]


@router.post(
    "",
    response_model=UserAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_account_route(
    payload: UserAccountCreate,
    db: SessionDependency,
    admin: AdminAccount,
) -> UserAccount:
    del admin
    return create_user_account(db, payload)


@router.get("", response_model=list[UserAccountResponse])
def list_user_accounts_route(
    db: SessionDependency,
    admin: AdminAccount,
    active: bool | None = None,
    role: UserRole | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[UserAccount]:
    del admin
    return list_user_accounts(
        db,
        active=active,
        role=role.value if role is not None else None,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/{account_id}", response_model=UserAccountResponse)
def get_user_account_route(
    account_id: int,
    db: SessionDependency,
    admin: AdminAccount,
) -> UserAccount:
    del admin
    return get_account_or_404(db, account_id)


@router.put("/{account_id}", response_model=UserAccountResponse)
def update_user_account_route(
    account_id: int,
    payload: UserAccountUpdate,
    db: SessionDependency,
    admin: AdminAccount,
) -> UserAccount:
    return update_user_account(db, account_id, payload, actor=admin)


@router.post(
    "/{account_id}/reset-password",
    response_model=UserAccountResponse,
)
def reset_user_password_route(
    account_id: int,
    payload: PasswordResetRequest,
    db: SessionDependency,
    admin: AdminAccount,
) -> UserAccount:
    del admin
    return reset_account_password(db, account_id, payload)
