from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    DatabaseOperationError,
    NotFoundError,
)
from app.core.security import hash_password, verify_password
from app.models import Person, UserAccount
from app.schemas.auth import (
    PasswordChangeRequest,
    PasswordResetRequest,
    UserAccountCreate,
    UserAccountUpdate,
)


def _account_statement():
    return select(UserAccount).options(selectinload(UserAccount.person))


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _raise_write_error(db: Session, exc: SQLAlchemyError) -> None:
    db.rollback()

    if isinstance(exc, IntegrityError):
        constraint = _constraint_name(exc)

        if constraint == "uq_user_account_username_ci":
            raise ConflictError("Ce nom d'utilisateur existe déjà.") from exc

        if constraint == "uq_user_account_person":
            raise ConflictError("Cette personne possède déjà un compte utilisateur.") from exc

        raise ConflictError(
            "Le compte ne peut pas être enregistré à cause d'une contrainte de données."
        ) from exc

    raise DatabaseOperationError(
        "Une erreur PostgreSQL est survenue pendant l'enregistrement du compte."
    ) from exc


def _get_employee_person(db: Session, person_id: int | None) -> Person | None:
    if person_id is None:
        return None

    person = db.get(Person, person_id)
    if person is None:
        raise NotFoundError("Personne associée introuvable.")

    if person.person_type != "EMPLOYEE":
        raise BusinessRuleError(
            "Un compte du dashboard peut être associé uniquement à un agent ONEE."
        )

    if not person.active:
        raise BusinessRuleError(
            "L'agent associé est désactivé et ne peut pas recevoir de compte."
        )

    return person


def _username_exists(
    db: Session,
    username: str,
    *,
    exclude_account_id: int | None = None,
) -> bool:
    statement = select(UserAccount.id).where(
        func.lower(func.btrim(UserAccount.username)) == username.lower().strip()
    )
    if exclude_account_id is not None:
        statement = statement.where(UserAccount.id != exclude_account_id)
    return db.scalar(statement.limit(1)) is not None


def get_account_or_404(db: Session, account_id: int) -> UserAccount:
    account = db.scalar(_account_statement().where(UserAccount.id == account_id))
    if account is None:
        raise NotFoundError("Compte utilisateur introuvable.")
    return account


def authenticate_account(
    db: Session,
    username: str,
    password: str,
) -> UserAccount | None:
    statement = _account_statement().where(
        func.lower(func.btrim(UserAccount.username)) == username.lower().strip()
    )

    try:
        account = db.scalar(statement)
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de vérifier le compte utilisateur."
        ) from exc

    if account is None or not verify_password(password, account.password_hash):
        return None

    if not account.active:
        return None

    account.last_login_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(account)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)

    return account


def create_user_account(
    db: Session,
    payload: UserAccountCreate,
) -> UserAccount:
    _get_employee_person(db, payload.person_id)

    if _username_exists(db, payload.username):
        raise ConflictError("Ce nom d'utilisateur existe déjà.")

    account = UserAccount(
        person_id=payload.person_id,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        active=payload.active,
    )
    db.add(account)

    try:
        db.commit()
        return get_account_or_404(db, account.id)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)
        raise AssertionError("Unreachable")


def list_user_accounts(
    db: Session,
    *,
    active: bool | None = None,
    role: str | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[UserAccount]:
    statement = _account_statement().order_by(UserAccount.username.asc())

    if active is not None:
        statement = statement.where(UserAccount.active.is_(active))

    if role is not None:
        statement = statement.where(UserAccount.role == role)

    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.outerjoin(Person, Person.id == UserAccount.person_id).where(
            func.concat_ws(
                " ",
                UserAccount.username,
                Person.first_name,
                Person.last_name,
            ).ilike(pattern)
        )

    try:
        return list(db.scalars(statement.offset(offset).limit(limit)).unique())
    except SQLAlchemyError as exc:
        raise DatabaseOperationError(
            "Impossible de consulter les comptes utilisateurs."
        ) from exc


def update_user_account(
    db: Session,
    account_id: int,
    payload: UserAccountUpdate,
    *,
    actor: UserAccount,
) -> UserAccount:
    account = get_account_or_404(db, account_id)
    updates: dict[str, Any] = payload.model_dump(exclude_unset=True)

    if "person_id" in updates:
        _get_employee_person(db, updates["person_id"])

    if "username" in updates:
        username = updates["username"]
        if _username_exists(db, username, exclude_account_id=account.id):
            raise ConflictError("Ce nom d'utilisateur existe déjà.")
        account.username = username

    if "person_id" in updates:
        account.person_id = updates["person_id"]

    if "role" in updates:
        new_role = updates["role"].value
        if account.id == actor.id and new_role != "ADMIN":
            raise BusinessRuleError(
                "Vous ne pouvez pas retirer votre propre rôle ADMIN."
            )
        account.role = new_role

    if "active" in updates:
        new_active = updates["active"]
        if account.id == actor.id and not new_active:
            raise BusinessRuleError(
                "Vous ne pouvez pas désactiver votre propre compte."
            )
        account.active = new_active

    try:
        db.commit()
        return get_account_or_404(db, account.id)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)
        raise AssertionError("Unreachable")


def reset_account_password(
    db: Session,
    account_id: int,
    payload: PasswordResetRequest,
) -> UserAccount:
    account = get_account_or_404(db, account_id)
    account.password_hash = hash_password(payload.new_password)

    try:
        db.commit()
        return get_account_or_404(db, account.id)
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)
        raise AssertionError("Unreachable")


def change_own_password(
    db: Session,
    account: UserAccount,
    payload: PasswordChangeRequest,
) -> None:
    if not verify_password(payload.current_password, account.password_hash):
        raise BusinessRuleError("Le mot de passe actuel est incorrect.")

    account.password_hash = hash_password(payload.new_password)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        _raise_write_error(db, exc)
