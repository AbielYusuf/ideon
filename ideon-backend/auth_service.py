"""Authentication business logic: registration, login, sessions, admin setup."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from typing import Any

import auth_store
import database
from auth import (
    SESSION_TTL_SECONDS,
    hash_password,
    hash_token,
    new_csrf_token,
    new_session_token,
    password_needs_rehash,
    validate_email,
    validate_password,
    validate_username,
    verify_dummy_password,
    verify_password,
)


class AuthError(ValueError):
    """Base class for expected authentication failures."""


class DuplicateEmailError(AuthError):
    pass


class DuplicateUsernameError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class InactiveAccountError(AuthError):
    pass


class AdminSetupError(AuthError):
    pass


def public_profile(user: dict[str, Any]) -> dict[str, Any]:
    """Strip password/session fields before returning a user."""
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "is_active": bool(user["is_active"]),
        "created_at": user["created_at"],
        "updated_at": user["updated_at"],
    }


def _seed_user_shortcuts(user_id: int) -> None:
    with closing(database.get_connection()) as connection:
        with connection:
            connection.executemany(
                """
                INSERT INTO web_shortcuts (user_id, name, url, category)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (user_id, name, url, category)
                    for name, url, category in database.DEFAULT_SHORTCUTS
                ],
            )


def _issue_session(user_id: int) -> tuple[str, str]:
    token = new_session_token()
    csrf_token = new_csrf_token()
    auth_store.purge_expired_sessions(int(time.time()))
    auth_store.create_session(
        user_id=user_id,
        token_hash=hash_token(token),
        csrf_hash=hash_token(csrf_token),
        expires_at=int(time.time()) + SESSION_TTL_SECONDS,
    )
    return token, csrf_token


def register(
    *,
    username: str,
    email: str,
    password: str,
    confirm_password: str,
) -> tuple[dict[str, Any], str, str]:
    username = validate_username(username)
    email = validate_email(email)
    validate_password(password)
    if password != confirm_password:
        raise AuthError("Passwords do not match.")

    if auth_store.get_user_by_email(email) is not None:
        raise DuplicateEmailError("An account with this email already exists.")
    if auth_store.get_user_by_username(username) is not None:
        raise DuplicateUsernameError("This username is already taken.")

    try:
        user = auth_store.create_user(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role="user",
        )
    except sqlite3.IntegrityError as error:
        # Race-safe fallback: report the conflicting unique field safely.
        if auth_store.get_user_by_email(email) is not None:
            raise DuplicateEmailError(
                "An account with this email already exists."
            ) from error
        raise DuplicateUsernameError("This username is already taken.") from error

    _seed_user_shortcuts(int(user["id"]))
    token, csrf_token = _issue_session(int(user["id"]))
    return public_profile(user), token, csrf_token


def login(email: str, password: str) -> tuple[dict[str, Any], str, str]:
    email = validate_email(email)
    user = auth_store.get_user_by_email(email)

    if user is None:
        verify_dummy_password(password)
        raise InvalidCredentialsError("Invalid email or password.")
    if not bool(user["is_active"]):
        raise InactiveAccountError("This account is disabled.")
    if not verify_password(user["password_hash"], password):
        raise InvalidCredentialsError("Invalid email or password.")

    if password_needs_rehash(user["password_hash"]):
        auth_store.update_password_hash(
            int(user["id"]), hash_password(password)
        )

    token, csrf_token = _issue_session(int(user["id"]))
    return public_profile(user), token, csrf_token


def logout(token: str | None) -> None:
    if token:
        auth_store.delete_session(hash_token(token))


def get_session_user(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    return auth_store.get_session_user(hash_token(token), int(time.time()))


def get_profile(user_id: int) -> dict[str, Any] | None:
    user = auth_store.get_user_by_id(user_id)
    return public_profile(user) if user else None


def create_initial_admin(
    *,
    username: str,
    email: str,
    password: str,
) -> tuple[dict[str, Any], bool]:
    """Create the first administrator and claim unowned legacy records.

    Returns ``(profile, created)``. If an administrator already exists the
    operation is a no-op apart from re-running the idempotent backfill.
    """
    username = validate_username(username)
    email = validate_email(email)
    validate_password(password)

    existing = auth_store.get_oldest_admin()
    if existing is not None:
        database.assign_legacy_records_to_admin(int(existing["id"]))
        return public_profile(existing), False

    if auth_store.get_user_by_email(email) is not None:
        raise AdminSetupError("A user with this email already exists.")
    if auth_store.get_user_by_username(username) is not None:
        raise AdminSetupError("A user with this username already exists.")

    try:
        user = auth_store.create_user(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role="admin",
        )
    except sqlite3.IntegrityError as error:
        raise AdminSetupError(
            "An account with this username or email already exists."
        ) from error

    database.assign_legacy_records_to_admin(int(user["id"]))
    return public_profile(user), True
