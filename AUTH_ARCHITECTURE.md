# Ideon Authentication & Data Ownership

This document records the ownership strategy that the authentication migration
implements. It is written before the schema migration.

## Identity model

- `users` is the identity table. Every human account has a unique username, a
  unique case-insensitive email, an Argon2id password hash, a role
  (`admin` | `user`), and an `is_active` flag.
- Sessions are server-managed. The browser receives an opaque random token in an
  HttpOnly cookie. SQLite stores only the SHA-256 hash of that token, the bound
  CSRF token hash, and an expiry timestamp.
- The authenticated user is resolved from the session cookie on every request.
  A user id is **never** accepted from the request body or query string for
  ownership decisions.

## Entity ownership

| Table | Ownership | Notes |
| --- | --- | --- |
| `ideas` | `user_id` | Primary private record. |
| `assessments` | `user_id` | Also linked to its idea; both filters are applied. |
| `improvement_sessions` | `user_id` | Linked to its idea. |
| `improvement_proposals` | `user_id` | Linked through its session. |
| `idea_revisions` | `user_id` | Linked through its session. |
| `web_shortcuts` | `user_id` | Personal Quick Access web links. |
| `websites`, `website_urls`, `website_activities` | Administrator-only | Organization operational data. Not user-private; every Website Tracker endpoint requires role `admin`. |
| `users`, `auth_sessions` | Identity / security | Never exposed through private-record APIs. |

Quick Access **local helper** configuration (`ideon-helper/config.json`) stays
machine-local. It is not copied into SQLite, is not returned by the backend, and
the local helper keeps its existing loopback binding, token, Origin and Host
protections. The desktop-application / local-project UI is restricted to
administrator accounts so local paths are not shared with ordinary accounts.

## Enforcement rules

- Every read and mutation of a private table includes `user_id = ?` in the SQL
  predicate. Missing rows return `404`, never `403`, so record existence is not
  leaked.
- Cross-record links are re-validated: an assessment cannot be attached to
  another user's idea; a proposal must belong to a session owned by the caller.
- Website Tracker endpoints require an authenticated administrator. Ordinary
  users receive `403` after successful authentication.
- `GET /api/health`, registration and login are the only public endpoints.

## Legacy migration

Existing installations have no users. The migration:

1. Creates `users` and `auth_sessions`.
2. Adds nullable `user_id` columns to all private tables, preserving ids,
   timestamps, foreign keys and history.
3. Leaves legacy rows unowned until an explicit administrator is created by
   `setup_admin.py` (or `IDEON_ADMIN_*` environment variables).
4. Assigns **all unowned legacy rows** to the oldest administrator, and only to
   that administrator. The step is idempotent and never overwrites a non-null
   owner.

Website Tracker tables, website ids and all 316 URL records are untouched by
this migration.

## Initial administrator setup

From `ideon-backend`, with the virtual environment active:

```powershell
# Optional: provide values non-interactively.
$env:IDEON_ADMIN_USERNAME = "admin"
$env:IDEON_ADMIN_EMAIL = "admin@example.com"
$env:IDEON_ADMIN_PASSWORD = "a-long-unique-password"
python setup_admin.py
```

`setup_admin.py` prompts for any missing value (password input is hidden),
validates the policy, creates the first `admin` account, and assigns every
unowned legacy private row to it. Running it again is safe: it keeps the
existing administrator and only claims rows that still have no owner.

Set `IDEON_COOKIE_SECURE=true` when serving over HTTPS.

## Roles

- `admin`: full personal workspace + Website Tracker + local helper UI.
- `user`: personal workspace only (ideas, assessments, improvement history,
  personal Quick Access web shortcuts).
