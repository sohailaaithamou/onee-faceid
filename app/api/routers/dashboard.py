from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth_dependencies import require_roles
from app.db.session import get_db
from app.models import UserAccount
from app.schemas.dashboard import DashboardOverview
from app.services.dashboard_service import get_dashboard_overview


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
SessionDependency = Annotated[Session, Depends(get_db)]
DashboardAccount = Annotated[
    UserAccount,
    Depends(require_roles("ADMIN", "RECEPTION", "VIEWER")),
]


@router.get(
    "/overview",
    response_model=DashboardOverview,
)
def dashboard_overview_route(
    db: SessionDependency,
    account: DashboardAccount,
    day: date | None = Query(
        default=None,
        description="Jour à analyser au format AAAA-MM-JJ. Par défaut : aujourd'hui.",
    ),
) -> DashboardOverview:
    del account
    return get_dashboard_overview(db, day=day)
