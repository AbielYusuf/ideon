"""Create the initial Ideon administrator and claim legacy records.

Usage (recommended, avoids shell history):

    python setup_admin.py

The command reads ``IDEON_ADMIN_USERNAME``, ``IDEON_ADMIN_EMAIL`` and
``IDEON_ADMIN_PASSWORD`` from the environment (or ``.env``) first and prompts
for anything missing. It never prints or stores the password in plaintext.

The operation is idempotent: if an administrator already exists, no new account
is created and only unowned legacy rows are assigned to the oldest admin.
"""

from __future__ import annotations

import getpass
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import database  # noqa: E402  (after load_dotenv)
from auth import PasswordPolicyError  # noqa: E402
from auth_service import AdminSetupError, create_initial_admin  # noqa: E402


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_field(name: str, prompt: str, *, secret: bool = False) -> str:
    value = _clean(os.environ.get(name))
    if value:
        return value
    if secret:
        return getpass.getpass(prompt)
    return input(prompt).strip()


def main() -> int:
    database.initialize_database()

    username = _read_field("IDEON_ADMIN_USERNAME", "Admin username: ")
    email = _read_field("IDEON_ADMIN_EMAIL", "Admin email: ")
    password = _read_field(
        "IDEON_ADMIN_PASSWORD",
        "Admin password (input hidden): ",
        secret=True,
    )

    if not username or not email or not password:
        print("Username, email and password are all required.", file=sys.stderr)
        return 2

    try:
        profile, created = create_initial_admin(
            username=username,
            email=email,
            password=password,
        )
    except (PasswordPolicyError, AdminSetupError, ValueError) as error:
        print(f"Administrator setup failed: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # pragma: no cover - defensive CLI boundary
        print(f"Unexpected failure: {error}", file=sys.stderr)
        return 1

    if created:
        print(f"Created administrator '{profile['username']}' (id {profile['id']}).")
    else:
        print(
            "An administrator already exists; kept it and re-ran the "
            f"idempotent legacy backfill for '{profile['username']}'."
        )
    print("Legacy private records now belong to the initial administrator.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
