"""Versioned per-match assessments linked to the existing internal match IDs."""

import sqlite3

from rocket_lantern.evaluations import Evaluation
from rocket_lantern.label_repository import LabelRepository
from rocket_lantern.labels import DEFAULT_LIST


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


def read_evaluation(connection: sqlite3.Connection, guid: str) -> str:
    """Absent assessments are unreviewed, not presumed free of smurfs."""
    return (
        LabelRepository(connection).choices(guid).get(DEFAULT_LIST, Evaluation.NOT_EVALUATED.value)
    )


def save_evaluation(connection: sqlite3.Connection, guid: str, value: str, updated_at: str) -> None:
    """Persist a vote even before the match result arrives, without inventing a result."""
    LabelRepository(connection).choose(guid, DEFAULT_LIST, value, updated_at)
