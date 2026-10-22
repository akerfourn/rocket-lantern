"""Recognize saved participants by stable ID, excluding the match being displayed."""

import sqlite3
from collections.abc import Sequence
from enum import StrEnum


class EncounterScope(StrEnum):
    """Prefer the active session over other saved encounters."""

    SESSION = "session"
    HISTORY = "history"


def read_player_encounters(
    connection: sqlite3.Connection,
    primary_ids: Sequence[str],
    *,
    player_id: str,
    session_id: int | None,
    exclude_match: str,
) -> dict[str, EncounterScope]:
    """Read only requested participants, preferring the tracked account's current session."""
    identifiers = sorted(set(primary_ids) - {"", player_id})
    if not identifiers:
        return {}
    placeholders = ", ".join("?" for _ in identifiers)
    rows = connection.execute(
        """
        SELECT p.primary_id, MAX(m.session_id IS NOT NULL) AS in_session
        FROM players p
        JOIN match_players mp ON mp.player_id = p.id
        JOIN match_details d ON d.id = mp.match_id
        LEFT JOIN matches m ON m.detail_id = d.id AND m.player_id = ? AND m.session_id = ?
        WHERE d.guid != ? AND p.primary_id IN ("""
        + placeholders
        + ") GROUP BY p.primary_id",
        (player_id, session_id, exclude_match, *identifiers),
    ).fetchall()
    encounters = {}
    for row in rows:
        scope = EncounterScope.HISTORY
        if row["in_session"]:
            scope = EncounterScope.SESSION
        encounters[row["primary_id"]] = scope
    return encounters
