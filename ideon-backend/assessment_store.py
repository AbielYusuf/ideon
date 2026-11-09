"""Persistence for completed assessments."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any

from database import get_connection


def insert_assessment_with_connection(
    connection: sqlite3.Connection,
    *,
    user_id: int,
    idea_id: int,
    idea_title: str,
    idea_description: str,
    analysis: dict[str, Any],
    scoring: dict[str, Any],
    final_score: float,
    classification: str,
) -> sqlite3.Row:
    """Insert a completed assessment within an existing transaction/connection."""
    cursor = connection.execute(
        """
        INSERT INTO assessments (
            user_id,
            idea_id,
            idea_title,
            idea_description,
            analysis_json,
            scoring_json,
            final_score,
            classification
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            idea_id,
            idea_title,
            idea_description,
            json.dumps(analysis, ensure_ascii=False),
            json.dumps(scoring, ensure_ascii=False),
            final_score,
            classification,
        ),
    )
    row = connection.execute(
        """
        SELECT id, user_id, idea_id, idea_title, idea_description, analysis_json,
               scoring_json, final_score, classification, created_at
        FROM assessments
        WHERE id = ? AND user_id = ?
        """,
        (cursor.lastrowid, user_id),
    ).fetchone()

    if row is None:
        raise sqlite3.Error("The assessment could not be loaded after saving.")

    return row


def insert_assessment(
    *,
    user_id: int,
    idea_id: int,
    idea_title: str,
    idea_description: str,
    analysis: dict[str, Any],
    scoring: dict[str, Any],
    final_score: float,
    classification: str,
) -> sqlite3.Row:
    """Insert a completed assessment and return the stored row."""
    with closing(get_connection()) as connection:
        with connection:
            return insert_assessment_with_connection(
                connection,
                user_id=user_id,
                idea_id=idea_id,
                idea_title=idea_title,
                idea_description=idea_description,
                analysis=analysis,
                scoring=scoring,
                final_score=final_score,
                classification=classification,
            )


def list_assessments(idea_id: int, user_id: int) -> list[sqlite3.Row]:
    """Return the caller's assessments for an idea, newest first."""
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, user_id, idea_id, idea_title, idea_description,
                   analysis_json, scoring_json, final_score, classification,
                   created_at
            FROM assessments
            WHERE idea_id = ? AND user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (idea_id, user_id),
        ).fetchall()

    return list(rows)
