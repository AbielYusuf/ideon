"""SQLite access layer for users and authentication sessions."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any

from database import get_connection

USER_COLUMNS = """
    id,
    username,
    email,
    password_hash,
    role,
    is_active,
    created_at,
    updated_at
"""


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def count_users() -> int:
    with closing(get_connection()) as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    return int(row["count"]) if row else 0


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            f"SELECT {USER_COLUMNS} FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_dict(row)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            f"""
            SELECT {USER_COLUMNS} FROM users
            WHERE lower(email) = lower(?)
            """,
            (email.strip(),),
        ).fetchone()
    return _row_to_dict(row)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            f"""
            SELECT {USER_COLUMNS} FROM users
            WHERE lower(username) = lower(?)
            """,
            (username.strip(),),
        ).fetchone()
    return _row_to_dict(row)


def create_user(
    *,
    username: str,
    email: str,
    password_hash: str,
    role: str = "user",
    is_active: bool = True,
) -> dict[str, Any]:
    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO users (username, email, password_hash, role, is_active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, email, password_hash, role, 1 if is_active else 0),
            )
            row = connection.execute(
                f"SELECT {USER_COLUMNS} FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    if row is None:
        raise sqlite3.Error("The user could not be loaded after creation.")
    return dict(row)


def update_password_hash(user_id: int, password_hash: str) -> None:
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """
                UPDATE users
                SET password_hash = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (password_hash, user_id),
            )


def get_oldest_admin() -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            f"""
            SELECT {USER_COLUMNS} FROM users
            WHERE role = 'admin'
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
    return _row_to_dict(row)


# ----------------------------------------------------------------------
# Sessions
# ----------------------------------------------------------------------


def create_session(
    *,
    user_id: int,
    token_hash: str,
    csrf_hash: str,
    expires_at: int,
) -> None:
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO auth_sessions (
                    user_id, token_hash, csrf_hash, expires_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (user_id, token_hash, csrf_hash, expires_at),
            )


def get_session_user(token_hash: str, now_epoch: int) -> dict[str, Any] | None:
    """Return the active user for an unexpired session token hash.

    Unowned or expired sessions are ignored. Expired rows are cleaned lazily.
    """
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT
                s.id AS session_id,
                s.csrf_hash,
                s.expires_at,
                u.id,
                u.username,
                u.email,
                u.password_hash,
                u.role,
                u.is_active,
                u.created_at,
                u.updated_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
              AND s.expires_at > ?
              AND u.is_active = 1
            """,
            (token_hash, now_epoch),
        ).fetchone()
        if row is None:
            connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ? AND expires_at <= ?",
                (token_hash, now_epoch),
            )
            connection.commit()
    return _row_to_dict(row)


def get_session_csrf_hash(token_hash: str) -> str | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT csrf_hash FROM auth_sessions WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
    return row["csrf_hash"] if row else None


def delete_session(token_hash: str) -> None:
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?",
                (token_hash,),
            )


def delete_user_sessions(user_id: int) -> None:
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE user_id = ?",
                (user_id,),
            )


def purge_expired_sessions(now_epoch: int) -> None:
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?",
                (now_epoch,),
            )
