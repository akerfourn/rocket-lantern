"""Persistent player sessions with stable IDs and a one-hour inactivity limit."""

import sqlite3
from datetime import datetime, timedelta


def create_session(connection: sqlite3.Connection, player_id: str, started_at: str) -> int:
    """Create a session inside the caller's transaction, including empty sessions."""
    cursor = connection.execute(
        "INSERT INTO sessions (player_id, started_at, last_activity_at) VALUES (?, ?, ?)",
        (player_id, started_at, started_at),
    )
    if cursor.lastrowid is None:
        raise sqlite3.DatabaseError("Could not create a session")
    return cursor.lastrowid


def current_session(connection: sqlite3.Connection, player_id: str, observed_at: str) -> int | None:
    """Find the most recently created session if it is still active."""
    row = connection.execute(
        "SELECT id, last_activity_at FROM sessions WHERE player_id = ? ORDER BY id DESC LIMIT 1",
        (player_id,),
    ).fetchone()
    if row is None:
        return None
    elapsed = datetime.fromisoformat(observed_at) - datetime.fromisoformat(row["last_activity_at"])
    if elapsed < timedelta(0) or elapsed >= timedelta(hours=1):
        return None
    return row["id"]


def assign_session(
    connection: sqlite3.Connection, match_id: str, player_id: str, observed_at: str
) -> int:
    """Keep existing membership on corrections; assign only newly observed matches."""
    existing = connection.execute(
        "SELECT session_id FROM matches WHERE match_id = ? AND player_id = ?",
        (match_id, player_id),
    ).fetchone()
    if existing is not None and existing["session_id"] is not None:
        return existing["session_id"]
    session_id = current_session(connection, player_id, observed_at)
    if session_id is None:
        session_id = create_session(connection, player_id, observed_at)
    connection.execute(
        "UPDATE sessions SET last_activity_at = ? WHERE id = ?", (observed_at, session_id)
    )
    return session_id


def migrate_sessions(connection: sqlite3.Connection) -> None:
    """Backfill legacy date-based groups once, atomically preserving all results."""
    if connection.execute("PRAGMA user_version").fetchone()[0] >= 2:
        return
    with connection:
        connection.execute("BEGIN")
        connection.execute(
            """
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                last_activity_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX sessions_player ON sessions(player_id, id)")
        connection.execute(
            "ALTER TABLE matches ADD COLUMN session_id INTEGER REFERENCES sessions(id)"
        )
        rows = connection.execute(
            "SELECT match_id, player_id, ended_at FROM matches ORDER BY player_id, ended_at, rowid"
        ).fetchall()
        for row in rows:
            session_id = assign_session(
                connection, row["match_id"], row["player_id"], row["ended_at"]
            )
            connection.execute(
                "UPDATE matches SET session_id = ? WHERE match_id = ? AND player_id = ?",
                (session_id, row["match_id"], row["player_id"]),
            )
        connection.execute("CREATE INDEX matches_session ON matches(player_id, session_id)")
        connection.execute("PRAGMA user_version = 2")
