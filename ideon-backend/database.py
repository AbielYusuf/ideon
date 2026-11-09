import sqlite3
from contextlib import closing
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent / "data" / "ideon.db"

# Canonical website registry. Insert order is stable and idempotent; the first
# entry is the legacy default used to associate pre-multi-website data.
WEBSITE_SEEDS: tuple[tuple[str, str], ...] = (
    ("EOS Teknologi", "eosteknologi.com"),
    ("EOS Indo Bisnis", "eosindobisnis.com"),
)

DEFAULT_WEBSITE_DOMAIN = WEBSITE_SEEDS[0][1]

DEFAULT_SHORTCUTS: tuple[tuple[str, str, str], ...] = (
    ("ChatGPT", "https://chatgpt.com", "AI & Research"),
    (
        "Google Search Console",
        "https://search.google.com/search-console",
        "Analytics & SEO",
    ),
    ("Google Analytics", "https://analytics.google.com", "Analytics & SEO"),
    ("EOS Teknologi Website", "https://eosteknologi.com", "Workspace & Company"),
)

# Private user-owned tables. Website Tracker operational data is intentionally
# not in this list: it is protected by an administrator role instead.
PRIVATE_USER_TABLES: tuple[str, ...] = (
    "ideas",
    "assessments",
    "improvement_sessions",
    "improvement_proposals",
    "idea_revisions",
    "web_shortcuts",
)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, name: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({name})").fetchall()
    }


def _sync_autoincrement_sequence(
    connection: sqlite3.Connection, table: str
) -> None:
    """Keep the next AUTOINCREMENT id above the highest preserved row id."""
    connection.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
    row = connection.execute(
        f"SELECT MAX(id) AS highest FROM {table}"
    ).fetchone()
    if row is not None and row["highest"] is not None:
        connection.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
            (table, row["highest"]),
        )


def _create_website_urls_table(
    connection: sqlite3.Connection, table: str
) -> None:
    connection.execute(
        f"""
        CREATE TABLE {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            website_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            sitemap_last_modified TEXT,
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            UNIQUE (website_id, url),
            FOREIGN KEY (website_id) REFERENCES websites(id)
        )
        """
    )


def _rebuild_website_urls(
    connection: sqlite3.Connection, default_website_id: int
) -> None:
    """Replace the legacy globally-unique URL table with a website-scoped one.

    Row ids, timestamps, sitemap metadata, and activity relationships are
    preserved. Foreign keys are disabled by the caller for this transaction.
    """
    connection.execute("DROP TABLE IF EXISTS website_urls_new")
    _create_website_urls_table(connection, "website_urls_new")
    connection.execute(
        """
        INSERT INTO website_urls_new (
            id, website_id, url, sitemap_last_modified, created_at, updated_at
        )
        SELECT id, ?, url, sitemap_last_modified, created_at, updated_at
        FROM website_urls
        """,
        (default_website_id,),
    )
    connection.execute("DROP TABLE website_urls")
    connection.execute("ALTER TABLE website_urls_new RENAME TO website_urls")
    connection.execute(
        "DELETE FROM sqlite_sequence WHERE name = 'website_urls_new'"
    )
    _sync_autoincrement_sequence(connection, "website_urls")


def _create_website_activities_table(
    connection: sqlite3.Connection, table: str
) -> None:
    connection.execute(
        f"""
        CREATE TABLE {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            activity_type TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('planned', 'completed')),
            website_id INTEGER,
            website_url_id INTEGER,
            planned_date TEXT NOT NULL,
            completed_date TEXT,
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            FOREIGN KEY (website_id) REFERENCES websites(id),
            FOREIGN KEY (website_url_id) REFERENCES website_urls(id)
                ON DELETE SET NULL
        )
        """
    )


def _initialize_website_tracker(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS websites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_websites_domain ON websites(domain)"
    )
    for name, domain in WEBSITE_SEEDS:
        connection.execute(
            """
            INSERT OR IGNORE INTO websites (name, domain)
            VALUES (?, ?)
            """,
            (name, domain),
        )

    default_website_id = connection.execute(
        "SELECT id FROM websites WHERE domain = ?",
        (DEFAULT_WEBSITE_DOMAIN,),
    ).fetchone()["id"]

    if not _table_exists(connection, "website_urls"):
        _create_website_urls_table(connection, "website_urls")
    else:
        columns = _table_columns(connection, "website_urls")
        if "website_id" not in columns:
            _rebuild_website_urls(connection, default_website_id)
        else:
            connection.execute(
                "UPDATE website_urls SET website_id = ? WHERE website_id IS NULL",
                (default_website_id,),
            )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_website_urls_website
        ON website_urls(website_id)
        """
    )

    if not _table_exists(connection, "website_activities"):
        _create_website_activities_table(connection, "website_activities")
    else:
        columns = _table_columns(connection, "website_activities")
        if "website_id" not in columns:
            connection.execute(
                """
                ALTER TABLE website_activities
                ADD COLUMN website_id INTEGER REFERENCES websites(id)
                """
            )

        # Derive the website from the associated URL where possible; general
        # legacy activities without a URL belonged to EOS Teknologi.
        connection.execute(
            """
            UPDATE website_activities
            SET website_id = (
                SELECT u.website_id FROM website_urls u
                WHERE u.id = website_activities.website_url_id
            )
            WHERE website_id IS NULL AND website_url_id IS NOT NULL
            """
        )
        connection.execute(
            "UPDATE website_activities SET website_id = ? WHERE website_id IS NULL",
            (default_website_id,),
        )

    for statement in (
        """
        CREATE INDEX IF NOT EXISTS idx_website_activities_planned_date
        ON website_activities(planned_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_website_activities_completed_date
        ON website_activities(completed_date)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_website_activities_status
        ON website_activities(status)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_website_activities_url
        ON website_activities(website_url_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_website_activities_website
        ON website_activities(website_id)
        """,
    ):
        connection.execute(statement)


def _create_auth_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
                CHECK(role IN ('admin', 'user')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            updated_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
        ON users(lower(email))
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
        ON users(lower(username))
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            csrf_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            ),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
        ON auth_sessions(user_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry
        ON auth_sessions(expires_at)
        """
    )


def _initialize_user_ownership(connection: sqlite3.Connection) -> None:
    """Add nullable ownership columns and backfill only when an admin exists."""
    ownership_columns = {
        "ideas": "user_id INTEGER REFERENCES users(id)",
        "assessments": "user_id INTEGER REFERENCES users(id)",
        "improvement_sessions": "user_id INTEGER REFERENCES users(id)",
        "improvement_proposals": "user_id INTEGER REFERENCES users(id)",
        "idea_revisions": "user_id INTEGER REFERENCES users(id)",
        "web_shortcuts": "user_id INTEGER REFERENCES users(id)",
    }
    indexes = {
        "ideas": "idx_ideas_user",
        "assessments": "idx_assessments_user",
        "improvement_sessions": "idx_improvement_sessions_user",
        "improvement_proposals": "idx_improvement_proposals_user",
        "idea_revisions": "idx_idea_revisions_user",
        "web_shortcuts": "idx_web_shortcuts_user",
    }

    for table, definition in ownership_columns.items():
        if not _table_exists(connection, table):
            continue
        if "user_id" not in _table_columns(connection, table):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS {indexes[table]} ON {table}(user_id)"
        )

    admin = connection.execute(
        "SELECT id FROM users WHERE role = 'admin' ORDER BY id ASC LIMIT 1"
    ).fetchone()
    if admin is not None:
        _assign_legacy_records(connection, admin["id"])


def _assign_legacy_records(
    connection: sqlite3.Connection, admin_id: int
) -> int:
    """Assign unowned legacy rows to the initial administrator only.

    Only NULL owners are touched, so repeated runs are safe and a real owner is
    never overwritten.
    """
    updated = 0
    for table in PRIVATE_USER_TABLES:
        if not _table_exists(connection, table):
            continue
        if "user_id" not in _table_columns(connection, table):
            continue
        cursor = connection.execute(
            f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL",
            (admin_id,),
        )
        updated += cursor.rowcount
    return updated


def assign_legacy_records_to_admin(admin_id: int) -> int:
    """Public idempotent version used by the administrator setup procedure."""
    with closing(get_connection()) as connection:
        with connection:
            return _assign_legacy_records(connection, admin_id)


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with closing(get_connection()) as connection:
        # The URL table rebuild must run without foreign-key enforcement so the
        # legacy table can be replaced while activity relationships are kept.
        connection.execute("PRAGMA foreign_keys = OFF")
        with connection:
            _create_auth_tables(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ideas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    updated_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    )
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idea_id INTEGER NOT NULL,
                    idea_title TEXT NOT NULL,
                    idea_description TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    scoring_json TEXT NOT NULL,
                    final_score REAL NOT NULL,
                    classification TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    )
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS improvement_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idea_id INTEGER NOT NULL,
                    base_assessment_id INTEGER NOT NULL,
                    current_revision_id INTEGER,
                    status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'cancelled')),
                    accepted_revision_count INTEGER NOT NULL DEFAULT 0 CHECK(accepted_revision_count >= 0 AND accepted_revision_count <= 5),
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    updated_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    FOREIGN KEY (idea_id) REFERENCES ideas(id) ON DELETE CASCADE,
                    FOREIGN KEY (base_assessment_id) REFERENCES assessments(id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS improvement_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    proposal_attempt INTEGER NOT NULL,
                    input_revision_id INTEGER,
                    input_assessment_id INTEGER NOT NULL,
                    proposed_title TEXT NOT NULL,
                    proposed_description TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    key_changes_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'accepted', 'rejected', 'superseded')),
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    FOREIGN KEY (session_id) REFERENCES improvement_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (input_assessment_id) REFERENCES assessments(id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS idea_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    proposal_id INTEGER NOT NULL UNIQUE,
                    revision_number INTEGER NOT NULL CHECK(revision_number >= 1 AND revision_number <= 5),
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    assessment_id INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    FOREIGN KEY (session_id) REFERENCES improvement_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (proposal_id) REFERENCES improvement_proposals(id),
                    FOREIGN KEY (assessment_id) REFERENCES assessments(id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_idea_active
                ON improvement_sessions(idea_id, status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_proposals_session
                ON improvement_proposals(session_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_revisions_session
                ON idea_revisions(session_id, revision_number)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS web_shortcuts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Custom',
                    created_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    ),
                    updated_at TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    )
                )
                """
            )
            _initialize_website_tracker(connection)
            # Seed default shortcuts if table is empty. They remain unowned
            # until the explicit administrator setup claims legacy records.
            count_cursor = connection.execute(
                "SELECT COUNT(*) AS count FROM web_shortcuts"
            )
            if count_cursor.fetchone()["count"] == 0:
                connection.executemany(
                    """
                    INSERT INTO web_shortcuts (name, url, category)
                    VALUES (?, ?, ?)
                    """,
                    DEFAULT_SHORTCUTS,
                )
            _initialize_user_ownership(connection)
