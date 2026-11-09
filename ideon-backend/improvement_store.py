"""Database access layer for Phase 5 Manual Improvement Loop."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any

from assessment_store import insert_assessment_with_connection
from database import get_connection


def create_session(
    *,
    user_id: int,
    idea_id: int,
    base_assessment_id: int,
) -> sqlite3.Row:
    """Create a new active improvement session."""
    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO improvement_sessions (
                    user_id,
                    idea_id,
                    base_assessment_id,
                    current_revision_id,
                    status,
                    accepted_revision_count
                )
                VALUES (?, ?, ?, NULL, 'active', 0)
                """,
                (user_id, idea_id, base_assessment_id),
            )
            row = connection.execute(
                """
                SELECT * FROM improvement_sessions
                WHERE id = ? AND user_id = ?
                """,
                (cursor.lastrowid, user_id),
            ).fetchone()

    if row is None:
        raise sqlite3.Error("Could not create improvement session.")
    return row


def get_session(session_id: int, user_id: int) -> sqlite3.Row | None:
    """Get an improvement session owned by the caller."""
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM improvement_sessions
            WHERE id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()


def get_active_session_for_idea(
    idea_id: int, user_id: int
) -> sqlite3.Row | None:
    """Get the caller's active improvement session for an idea if one exists."""
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM improvement_sessions
            WHERE idea_id = ? AND user_id = ? AND status = 'active'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (idea_id, user_id),
        ).fetchone()


def list_sessions_for_idea(idea_id: int, user_id: int) -> list[sqlite3.Row]:
    """List the caller's improvement sessions for an idea."""
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM improvement_sessions
            WHERE idea_id = ? AND user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (idea_id, user_id),
        ).fetchall()


def update_session_status(session_id: int, user_id: int, status: str) -> None:
    """Update session status (completed or cancelled)."""
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """
                UPDATE improvement_sessions
                SET status = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND user_id = ?
                """,
                (status, session_id, user_id),
            )


def insert_proposal(
    *,
    user_id: int,
    session_id: int,
    proposal_attempt: int,
    input_revision_id: int | None,
    input_assessment_id: int,
    proposed_title: str,
    proposed_description: str,
    rationale: str,
    key_changes: list[str],
) -> sqlite3.Row:
    """Insert a new pending improvement proposal."""
    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO improvement_proposals (
                    user_id,
                    session_id,
                    proposal_attempt,
                    input_revision_id,
                    input_assessment_id,
                    proposed_title,
                    proposed_description,
                    rationale,
                    key_changes_json,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    user_id,
                    session_id,
                    proposal_attempt,
                    input_revision_id,
                    input_assessment_id,
                    proposed_title,
                    proposed_description,
                    rationale,
                    json.dumps(key_changes, ensure_ascii=False),
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM improvement_proposals
                WHERE id = ? AND user_id = ?
                """,
                (cursor.lastrowid, user_id),
            ).fetchone()

    if row is None:
        raise sqlite3.Error("Could not save proposal.")
    return row


def get_proposal(proposal_id: int, user_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM improvement_proposals
            WHERE id = ? AND user_id = ?
            """,
            (proposal_id, user_id),
        ).fetchone()


def get_pending_proposal(session_id: int, user_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM improvement_proposals
            WHERE session_id = ? AND user_id = ? AND status = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, user_id),
        ).fetchone()


def list_proposals(session_id: int, user_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM improvement_proposals
            WHERE session_id = ? AND user_id = ?
            ORDER BY proposal_attempt ASC, id ASC
            """,
            (session_id, user_id),
        ).fetchall()


def supersede_pending_proposals(session_id: int, user_id: int) -> None:
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """
                UPDATE improvement_proposals
                SET status = 'superseded'
                WHERE session_id = ? AND user_id = ? AND status = 'pending'
                """,
                (session_id, user_id),
            )


def update_proposal_status(
    proposal_id: int, user_id: int, status: str
) -> None:
    with closing(get_connection()) as connection:
        with connection:
            connection.execute(
                """
                UPDATE improvement_proposals
                SET status = ?
                WHERE id = ? AND user_id = ?
                """,
                (status, proposal_id, user_id),
            )


def get_next_proposal_attempt(session_id: int, user_id: int) -> int:
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(proposal_attempt), 0) + 1 AS next_attempt
            FROM improvement_proposals
            WHERE session_id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()
        return int(row["next_attempt"]) if row else 1


def list_revisions(session_id: int, user_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM idea_revisions
            WHERE session_id = ? AND user_id = ?
            ORDER BY revision_number ASC
            """,
            (session_id, user_id),
        ).fetchall()


def get_revision(revision_id: int, user_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM idea_revisions
            WHERE id = ? AND user_id = ?
            """,
            (revision_id, user_id),
        ).fetchone()


def get_assessment_by_id(assessment_id: int, user_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as connection:
        return connection.execute(
            """
            SELECT * FROM assessments
            WHERE id = ? AND user_id = ?
            """,
            (assessment_id, user_id),
        ).fetchone()


def atomic_accept_proposal(
    *,
    user_id: int,
    session_id: int,
    proposal_id: int,
    idea_id: int,
    proposed_title: str,
    proposed_description: str,
    analysis_payload: dict[str, Any],
    scoring_payload: dict[str, Any],
    final_score: float,
    classification: str,
) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row]:
    """Atomically commit assessment, revision, proposal status, and session update.

    Returns:
        (updated_session_row, updated_proposal_row, new_revision_row)
    """
    with closing(get_connection()) as connection:
        with connection:
            # 1. Re-validate session ownership/state inside transaction
            session_row = connection.execute(
                """
                SELECT * FROM improvement_sessions
                WHERE id = ? AND user_id = ?
                """,
                (session_id, user_id),
            ).fetchone()

            if session_row is None:
                raise ValueError("Session not found.")
            if session_row["status"] != "active":
                raise ValueError(
                    f"Session is not active (current status: {session_row['status']})."
                )
            if session_row["accepted_revision_count"] >= 5:
                raise ValueError("Maximum 5 accepted revisions reached.")

            # 2. Re-validate proposal ownership inside transaction
            proposal_row = connection.execute(
                """
                SELECT * FROM improvement_proposals
                WHERE id = ? AND user_id = ?
                """,
                (proposal_id, user_id),
            ).fetchone()

            if proposal_row is None:
                raise ValueError("Proposal not found.")
            if proposal_row["session_id"] != session_id:
                raise ValueError("Proposal does not belong to this session.")
            if proposal_row["status"] != "pending":
                raise ValueError(
                    f"Proposal is no longer pending (current status: {proposal_row['status']})."
                )

            # 3. Insert assessment using existing reusable helper
            assessment_row = insert_assessment_with_connection(
                connection,
                user_id=user_id,
                idea_id=idea_id,
                idea_title=proposed_title,
                idea_description=proposed_description,
                analysis=analysis_payload,
                scoring=scoring_payload,
                final_score=final_score,
                classification=classification,
            )
            new_assessment_id = assessment_row["id"]

            # 4. Insert idea revision
            next_rev_num = session_row["accepted_revision_count"] + 1
            rev_cursor = connection.execute(
                """
                INSERT INTO idea_revisions (
                    user_id,
                    session_id,
                    proposal_id,
                    revision_number,
                    title,
                    description,
                    assessment_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    session_id,
                    proposal_id,
                    next_rev_num,
                    proposed_title,
                    proposed_description,
                    new_assessment_id,
                ),
            )
            new_revision_id = rev_cursor.lastrowid

            # 5. Update proposal status
            connection.execute(
                """
                UPDATE improvement_proposals
                SET status = 'accepted'
                WHERE id = ? AND user_id = ?
                """,
                (proposal_id, user_id),
            )

            # 6. Update session state
            new_status = "completed" if next_rev_num == 5 else "active"
            connection.execute(
                """
                UPDATE improvement_sessions
                SET current_revision_id = ?,
                    accepted_revision_count = ?,
                    status = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND user_id = ?
                """,
                (new_revision_id, next_rev_num, new_status, session_id, user_id),
            )

            # Reload updated rows
            updated_session = connection.execute(
                "SELECT * FROM improvement_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
            updated_proposal = connection.execute(
                "SELECT * FROM improvement_proposals WHERE id = ? AND user_id = ?",
                (proposal_id, user_id),
            ).fetchone()
            new_revision = connection.execute(
                "SELECT * FROM idea_revisions WHERE id = ? AND user_id = ?",
                (new_revision_id, user_id),
            ).fetchone()

            return updated_session, updated_proposal, new_revision
