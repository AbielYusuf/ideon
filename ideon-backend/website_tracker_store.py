"""SQLite access layer for Website Tracker."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any

from database import get_connection

ACTIVITY_COLUMNS = """
    a.id,
    a.title,
    a.description,
    a.activity_type,
    a.status,
    a.website_id,
    w.name AS website_name,
    a.website_url_id,
    u.url AS website_url,
    a.planned_date,
    a.completed_date,
    a.created_at,
    a.updated_at
"""

URL_AGGREGATE_COLUMNS = """
    u.id,
    u.website_id,
    w.name AS website_name,
    w.domain AS website_domain,
    u.url,
    u.sitemap_last_modified,
    u.created_at,
    u.updated_at,
    COUNT(a.id) AS activity_count,
    COALESCE(SUM(CASE WHEN a.status = 'planned' THEN 1 ELSE 0 END), 0) AS planned_count,
    COALESCE(SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_count,
    MAX(CASE WHEN a.status = 'completed'
        THEN COALESCE(a.completed_date, a.planned_date)
        ELSE a.planned_date END) AS last_activity_date
"""

ACTIVITY_JOINS = """
    LEFT JOIN website_urls u ON u.id = a.website_url_id
    LEFT JOIN websites w ON w.id = a.website_id
"""

_SORT_COLUMNS = {
    "url": "u.url",
    "activity_count": "activity_count",
    "last_activity": "last_activity_date",
    "created_at": "u.created_at",
}


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# ----------------------------------------------------------------------
# Websites
# ----------------------------------------------------------------------

_WEBSITE_COLUMNS = """
    w.id,
    w.name,
    w.domain,
    w.created_at,
    w.updated_at,
    (SELECT COUNT(*) FROM website_urls u WHERE u.website_id = w.id) AS url_count,
    (SELECT COUNT(*) FROM website_activities a WHERE a.website_id = w.id) AS activity_count
"""


def list_websites() -> list[dict[str, Any]]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            f"""
            SELECT {_WEBSITE_COLUMNS}
            FROM websites w
            ORDER BY w.id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_website(website_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            f"""
            SELECT {_WEBSITE_COLUMNS}
            FROM websites w
            WHERE w.id = ?
            """,
            (website_id,),
        ).fetchone()
    return _row_to_dict(row)


def get_website_by_domain(domain: str) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            f"""
            SELECT {_WEBSITE_COLUMNS}
            FROM websites w
            WHERE lower(w.domain) = lower(?)
            """,
            (domain,),
        ).fetchone()
    return _row_to_dict(row)


# ----------------------------------------------------------------------
# URLs
# ----------------------------------------------------------------------


def list_urls(
    *,
    website_id: int | None = None,
    search: str | None = None,
    status: str | None = None,
    sort: str = "url",
    order: str = "asc",
) -> list[dict[str, Any]]:
    where: list[str] = []
    parameters: list[Any] = []

    if website_id is not None:
        where.append("u.website_id = ?")
        parameters.append(website_id)

    if search:
        escaped = (
            search.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        where.append("u.url LIKE ? ESCAPE '\\'")
        parameters.append(f"%{escaped}%")

    having: list[str] = []
    if status == "planned":
        having.append("planned_count > 0")
    elif status == "completed":
        having.append("completed_count > 0")

    sort_column = _SORT_COLUMNS.get(sort, _SORT_COLUMNS["url"])
    direction = "DESC" if order.lower() == "desc" else "ASC"

    query = f"""
        SELECT {URL_AGGREGATE_COLUMNS}
        FROM website_urls u
        JOIN websites w ON w.id = u.website_id
        LEFT JOIN website_activities a ON a.website_url_id = u.id
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " GROUP BY u.id"
    if having:
        query += " HAVING " + " AND ".join(having)
    query += f" ORDER BY {sort_column} {direction}, u.url ASC"

    with closing(get_connection()) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_url(url_id: int, website_id: int | None = None) -> dict[str, Any] | None:
    where = ["u.id = ?"]
    parameters: list[Any] = [url_id]
    if website_id is not None:
        where.append("u.website_id = ?")
        parameters.append(website_id)

    with closing(get_connection()) as connection:
        row = connection.execute(
            f"""
            SELECT {URL_AGGREGATE_COLUMNS}
            FROM website_urls u
            JOIN websites w ON w.id = u.website_id
            LEFT JOIN website_activities a ON a.website_url_id = u.id
            WHERE {' AND '.join(where)}
            GROUP BY u.id
            """,
            parameters,
        ).fetchone()
    return _row_to_dict(row)


def get_url_by_url(website_id: int, url: str) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT id, website_id, url, sitemap_last_modified, created_at, updated_at
            FROM website_urls
            WHERE website_id = ? AND url = ?
            """,
            (website_id, url),
        ).fetchone()
    return _row_to_dict(row)


# ----------------------------------------------------------------------
# Activities
# ----------------------------------------------------------------------


def list_activities_for_url(url_id: int) -> list[dict[str, Any]]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            f"""
            SELECT {ACTIVITY_COLUMNS}
            FROM website_activities a
            {ACTIVITY_JOINS}
            WHERE a.website_url_id = ?
            ORDER BY
                COALESCE(a.completed_date, a.planned_date) ASC,
                a.planned_date ASC,
                a.id ASC
            """,
            (url_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_activities(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    activity_type: str | None = None,
    website_id: int | None = None,
    website_url_id: int | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    parameters: list[Any] = []

    if start_date and end_date:
        where.append(
            """
            (
                (a.planned_date BETWEEN ? AND ?)
                OR (a.completed_date IS NOT NULL AND a.completed_date BETWEEN ? AND ?)
            )
            """
        )
        parameters.extend([start_date, end_date, start_date, end_date])
    elif start_date:
        where.append("(a.planned_date >= ? OR a.completed_date >= ?)")
        parameters.extend([start_date, start_date])
    elif end_date:
        where.append("(a.planned_date <= ? OR a.completed_date <= ?)")
        parameters.extend([end_date, end_date])

    if status in {"planned", "completed"}:
        where.append("a.status = ?")
        parameters.append(status)
    if activity_type:
        where.append("a.activity_type = ?")
        parameters.append(activity_type)
    if website_id is not None:
        where.append("a.website_id = ?")
        parameters.append(website_id)
    if website_url_id is not None:
        where.append("a.website_url_id = ?")
        parameters.append(website_url_id)

    query = f"""
        SELECT {ACTIVITY_COLUMNS}
        FROM website_activities a
        {ACTIVITY_JOINS}
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += """
        ORDER BY
            COALESCE(a.completed_date, a.planned_date) ASC,
            a.planned_date ASC,
            a.id ASC
    """

    with closing(get_connection()) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_activity(activity_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            f"""
            SELECT {ACTIVITY_COLUMNS}
            FROM website_activities a
            {ACTIVITY_JOINS}
            WHERE a.id = ?
            """,
            (activity_id,),
        ).fetchone()
    return _row_to_dict(row)


def create_activity(
    *,
    title: str,
    description: str,
    activity_type: str,
    status: str,
    website_id: int,
    website_url_id: int | None,
    planned_date: str,
    completed_date: str | None,
) -> dict[str, Any]:
    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO website_activities (
                    title, description, activity_type, status,
                    website_id, website_url_id, planned_date, completed_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    description,
                    activity_type,
                    status,
                    website_id,
                    website_url_id,
                    planned_date,
                    completed_date,
                ),
            )
            row = connection.execute(
                f"""
                SELECT {ACTIVITY_COLUMNS}
                FROM website_activities a
                {ACTIVITY_JOINS}
                WHERE a.id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()

    if row is None:
        raise sqlite3.Error("The activity could not be loaded after creation.")
    return dict(row)


def update_activity(activity_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
    if not changes:
        return get_activity(activity_id)

    allowed = {
        "title",
        "description",
        "activity_type",
        "status",
        "website_id",
        "website_url_id",
        "planned_date",
        "completed_date",
    }
    assignments: list[str] = []
    parameters: list[Any] = []
    for key, value in changes.items():
        if key not in allowed:
            continue
        assignments.append(f"{key} = ?")
        parameters.append(value)

    if not assignments:
        return get_activity(activity_id)

    assignments.append("updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
    parameters.append(activity_id)

    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                f"""
                UPDATE website_activities
                SET {', '.join(assignments)}
                WHERE id = ?
                """,
                parameters,
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                f"""
                SELECT {ACTIVITY_COLUMNS}
                FROM website_activities a
                {ACTIVITY_JOINS}
                WHERE a.id = ?
                """,
                (activity_id,),
            ).fetchone()

    return _row_to_dict(row)


def delete_activity(activity_id: int) -> bool:
    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM website_activities WHERE id = ?",
                (activity_id,),
            )
    return cursor.rowcount > 0


def import_urls(
    website_id: int, records: list[tuple[str, str | None]]
) -> tuple[int, int, int]:
    """Insert website-scoped URLs, preserving existing rows and history.

    Returns ``(imported, duplicates, updated)``. A record is counted as
    ``updated`` when it already exists and its sitemap metadata changed;
    otherwise an existing record is counted as a ``duplicate``.
    """
    imported = 0
    duplicates = 0
    updated = 0

    with closing(get_connection()) as connection:
        with connection:
            for url, last_modified in records:
                existing = connection.execute(
                    """
                    SELECT id, sitemap_last_modified
                    FROM website_urls
                    WHERE website_id = ? AND url = ?
                    """,
                    (website_id, url),
                ).fetchone()

                if existing is not None:
                    if (
                        last_modified
                        and last_modified != existing["sitemap_last_modified"]
                    ):
                        connection.execute(
                            """
                            UPDATE website_urls
                            SET sitemap_last_modified = ?,
                                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                            WHERE id = ?
                            """,
                            (last_modified, existing["id"]),
                        )
                        updated += 1
                    else:
                        duplicates += 1
                    continue

                connection.execute(
                    """
                    INSERT INTO website_urls (website_id, url, sitemap_last_modified)
                    VALUES (?, ?, ?)
                    """,
                    (website_id, url, last_modified),
                )
                imported += 1

    return imported, duplicates, updated
