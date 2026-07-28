from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.core.exceptions import AppError
from app.db.session import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ONEE Face ID API",
    version="1.0.0",
)

app.include_router(api_router)

STATIC_ROOT = Path(__file__).resolve().parent / "static"
DASHBOARD_ROOT = STATIC_ROOT / "dashboard"
app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="static")


@app.exception_handler(AppError)
async def app_error_handler(
    request: Request,
    exc: AppError,
) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "API ONEE Face ID opérationnelle",
        "login": "/login",
        "dashboard": "/dashboard",
        "documentation": "/docs",
    }


@app.get("/login", include_in_schema=False, response_class=FileResponse)
def login_page() -> FileResponse:
    return FileResponse(DASHBOARD_ROOT / "login.html")


@app.get("/dashboard", include_in_schema=False, response_class=FileResponse)
def dashboard_page() -> FileResponse:
    return FileResponse(DASHBOARD_ROOT / "index.html")


@app.get("/dashboard/", include_in_schema=False)
def dashboard_slash_redirect() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@app.get("/health/db")
def database_health(
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        result = db.execute(
            text(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS database_user,
                    current_schema() AS database_schema
                """
            )
        ).mappings().one()
    except SQLAlchemyError as exc:
        logger.exception("Erreur de connexion à PostgreSQL")
        raise HTTPException(
            status_code=500,
            detail="Connexion PostgreSQL impossible",
        ) from exc

    return {
        "status": "ok",
        "database": str(result["database_name"]),
        "user": str(result["database_user"]),
        "schema": str(result["database_schema"]),
    }
