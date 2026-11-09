"""Password, token, cookie, and validation primitives for Ideon authentication."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

SESSION_COOKIE = "ideon_session"
CSRF_COOKIE = "ideon_csrf"

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SESSION_TTL_SECONDS = max(
    300, int(os.environ.get("IDEON_SESSION_TTL_HOURS", "168")) * 3600
)

_TRUTHY = {"1", "true", "yes", "on"}
COOKIE_SECURE = (
    os.environ.get("IDEON_COOKIE_SECURE", "").strip().lower() in _TRUTHY
    or os.environ.get("IDEON_ENV", "").strip().lower() == "production"
)
# The deployed frontend and API live on different sites (Vercel and the
# Cloudflare Tunnel), so production auth cookies must be allowed on
# cross-site fetches. Local HTTP development keeps the browser-compatible
# lax setting because SameSite=None requires Secure.
COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"

# Argon2id is the PasswordHasher default. Explicit parameters keep hashes stable
# and document the memory cost used at rest.
_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

# Used to keep login timing similar when the email does not exist.
_DUMMY_HASH = _HASHER.hash("ideon-dummy-password-for-timing")


class PasswordPolicyError(ValueError):
    """The supplied password does not meet the minimum policy."""


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> None:
    """Burn comparable time for unknown accounts without leaking existence."""
    try:
        _HASHER.verify(_DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password(password: str) -> str:
    """Return the password when valid, otherwise raise a safe error."""
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be a string.")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {PASSWORD_MAX_LENGTH} characters long."
        )
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise PasswordPolicyError(
            "Password must contain at least one letter and one number."
        )
    if password.strip() != password:
        raise PasswordPolicyError("Password must not begin or end with whitespace.")
    return password


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if len(normalized) > 254 or not EMAIL_PATTERN.match(normalized):
        raise PasswordPolicyError("Enter a valid email address.")
    return normalized


def validate_username(username: str) -> str:
    cleaned = username.strip()
    if not (USERNAME_MIN_LENGTH <= len(cleaned) <= USERNAME_MAX_LENGTH):
        raise PasswordPolicyError(
            f"Username must be between {USERNAME_MIN_LENGTH} and "
            f"{USERNAME_MAX_LENGTH} characters."
        )
    if not USERNAME_PATTERN.match(cleaned):
        raise PasswordPolicyError(
            "Username may only contain letters, numbers, dots, hyphens and underscores."
        )
    return cleaned


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def set_auth_cookies(response: Any, token: str, csrf_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    # Readable by the SPA so it can echo the value in X-CSRF-Token.
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=SESSION_TTL_SECONDS,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookies(response: Any) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
