"""Versioned per-match assessments linked to the existing internal match IDs."""

import sqlite3

from rocket_lantern.evaluations import Evaluation
from rocket_lantern.match_repository import match_key


def migrate_evaluations(connection: sqlite3.Connection) -> None:
    """Add assessments without changing historical results or sessions."""
    if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
        return
    with connection:
        connection.execute("BEGIN")
        connection.execute(
            """
            CREATE TABLE match_evaluations (
                match_id INTEGER PRIMARY KEY REFERENCES match_details(id),
                evaluation TEXT NOT NULL CHECK (
                    evaluation IN ('not_evaluated', 'no_suspicion', 'possible', 'strong')
                ),
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute("PRAGMA user_version = 3")


def read_evaluation(connection: sqlite3.Connection, guid: str) -> Evaluation:
    """Absent assessments are unreviewed, not presumed free of smurfs."""
    row = connection.execute(
        """
        SELECT e.evaluation FROM match_evaluations e
        JOIN match_details d ON d.id = e.match_id WHERE d.guid = ?
        """,
        (guid,),
    ).fetchone()
    if row is None:
        return Evaluation.NOT_EVALUATED
    return Evaluation(row[0])


def save_evaluation(
    connection: sqlite3.Connection, guid: str, value: Evaluation, updated_at: str
) -> None:
    """Persist a vote even before the match result arrives, without inventing a result."""
    if not isinstance(guid, str) or not guid.strip():
        raise ValueError("A match GUID is required")
    value = Evaluation(value)
    with connection:
        match_id = match_key(connection, guid)
        connection.execute(
            """
            INSERT INTO match_evaluations (match_id, evaluation, updated_at) VALUES (?, ?, ?)
            ON CONFLICT (match_id) DO UPDATE SET
                evaluation = excluded.evaluation, updated_at = excluded.updated_at
            """,
            (match_id, value.value, updated_at),
        )
