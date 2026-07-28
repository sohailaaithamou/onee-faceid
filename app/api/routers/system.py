from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth_dependencies import require_roles
from app.db.session import get_db
from app.models import UserAccount
from app.schemas.system import SystemReadiness
from app.services.system_service import get_system_readiness


router = APIRouter(prefix="/system", tags=["System validation"])
SessionDependency = Annotated[Session, Depends(get_db)]
AdminAccount = Annotated[
    UserAccount,
    Depends(require_roles("ADMIN")),
]


@router.get(
    "/readiness",
    response_model=SystemReadiness,
    summary="Vérifier si le prototype est prêt",
)
def system_readiness_route(
    db: SessionDependency,
    account: AdminAccount,
) -> SystemReadiness:
    del account
    return get_system_readiness(db)
