from __future__ import annotations


class AppError(Exception):
    """Erreur métier contrôlée et affichable par l'API."""

    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class BusinessRuleError(AppError):
    status_code = 422


class DatabaseOperationError(AppError):
    status_code = 500
