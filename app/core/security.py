from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.auth_settings import auth_settings
from app.models import UserAccount


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return password_hash.verify(password, encoded_hash)
    except Exception:
        return False


def create_access_token(account: UserAccount) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(minutes=auth_settings.access_token_minutes)
    expires_at = now + expires_delta

    payload: dict[str, Any] = {
        "sub": str(account.id),
        "username": account.username,
        "role": account.role,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "iss": auth_settings.issuer,
        "aud": auth_settings.audience,
    }

    token = jwt.encode(
        payload,
        auth_settings.secret_key,
        algorithm=auth_settings.algorithm,
    )
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            auth_settings.secret_key,
            algorithms=[auth_settings.algorithm],
            audience=auth_settings.audience,
            issuer=auth_settings.issuer,
            options={
                "require": ["sub", "exp", "iat", "nbf", "iss", "aud"],
            },
        )
    except InvalidTokenError as exc:
        raise ValueError("Jeton d'accès invalide ou expiré.") from exc
