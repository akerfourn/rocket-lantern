"""Repair premature results only when saved match events establish the real ending."""

import json
import sqlite3

REPAIR_KEY = "premature_results_repaired_v1"


def repair_premature_results(connection: sqlite3.Connection, guid: str | None = None) -> int:
    """Scan history once, or one match when its end arrives after upgrading."""
    if guid is None:
        if connection.execute("SELECT 1 FROM settings WHERE key = ?", (REPAIR_KEY,)).fetchone():
            return 0
    match_filter = ""
    parameters: tuple[str, ...] = ()
    if guid is not None:
        match_filter = " AND m.match_id = ?"
        parameters = (guid,)
    candidates = connection.execute(
        """SELECT m.rowid AS result_id, m.detail_id, m.player_ref, m.ended_at,
                  m.session_id, p.team, d.winner, e.observed_at AS actual_end, e.details_json
           FROM matches m
           JOIN match_details d ON d.id = m.detail_id
           JOIN match_players p ON p.match_id = m.detail_id AND p.player_id = m.player_ref
           JOIN match_events e ON e.match_id = m.detail_id AND e.kind = 'MatchEnded'
           WHERE m.outcome IN ('win', 'loss') AND p.team IN (0, 1)
             AND d.winner IN (0, 1)
             AND EXISTS (
               SELECT 1 FROM match_events start
               WHERE start.match_id = m.detail_id AND start.kind = 'RoundStarted'
                 AND julianday(start.observed_at) > julianday(m.ended_at)
                 AND julianday(start.observed_at) < julianday(e.observed_at)
             )
        """
        + match_filter
        + " ORDER BY m.rowid, julianday(e.observed_at), e.id",
        parameters,
    ).fetchall()
    repaired: set[int] = set()
    with connection:
        for row in candidates:
            if row["result_id"] in repaired or not _has_confirmed_ending(connection, row):
                continue
            outcome = "loss"
            if row["team"] == row["winner"]:
                outcome = "win"
            connection.execute(
                "UPDATE matches SET outcome = ?, ended_at = ? WHERE rowid = ?",
                (outcome, row["actual_end"], row["result_id"]),
            )
            connection.execute(
                """UPDATE sessions SET last_activity_at = ?
                   WHERE id = ? AND julianday(last_activity_at) < julianday(?)""",
                (row["actual_end"], row["session_id"], row["actual_end"]),
            )
            repaired.add(row["result_id"])
        if guid is None:
            connection.execute("INSERT INTO settings VALUES (?, ?)", (REPAIR_KEY, "1"))
    return len(repaired)


def _has_confirmed_ending(connection: sqlite3.Connection, row: sqlite3.Row) -> bool:
    try:
        details = json.loads(row["details_json"])
    except (ValueError, TypeError):
        return False
    if not isinstance(details, dict):
        return False
    winner = details.get("WinnerTeamNum")
    if type(winner) is not int or winner != row["winner"]:
        return False
    last_team = connection.execute(
        """SELECT ep.team FROM match_event_players ep
           JOIN match_events e ON e.id = ep.event_id
           WHERE e.match_id = ? AND ep.player_id = ? AND ep.team IN (0, 1)
             AND julianday(e.observed_at) >= julianday(?)
             AND julianday(e.observed_at) <= julianday(?)
           ORDER BY julianday(e.observed_at) DESC, e.id DESC, ep.position DESC LIMIT 1""",
        (row["detail_id"], row["player_ref"], row["ended_at"], row["actual_end"]),
    ).fetchone()
    return last_team is not None and last_team["team"] == row["team"]
