"""Small SQLite repository; each match is counted once per selected player."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from rl_winloose.tracker import MatchResult


@dataclass(frozen=True)
class Summary:
    """Counts for a player's complete saved history."""

    wins: int
    losses: int
    unknown: int

    @property
    def win_rate(self) -> float:
        """Return the win percentage, excluding unknown results."""
        completed = self.wins + self.losses
        if completed == 0:
            return 0.0
        return 100 * self.wins / completed


class MatchStore:
    """Own the connection and expose only parameterized database operations."""

    def __init__(self, path: Path | str) -> None:
        self.connection = sqlite3.connect(path, timeout=5)
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS matches (
                    match_id TEXT NOT NULL,
                    player_id TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    playlist INTEGER,
                    outcome TEXT NOT NULL CHECK (outcome IN ('win', 'loss', 'unknown')),
                    PRIMARY KEY (match_id, player_id)
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def save(self, result: MatchResult) -> None:
        """Allow a confirmed result to replace an unknown, never the reverse."""
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO matches VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (match_id, player_id) DO UPDATE SET
                    ended_at = excluded.ended_at,
                    playlist = excluded.playlist,
                    outcome = excluded.outcome
                WHERE matches.outcome = 'unknown' AND excluded.outcome != 'unknown'
                """,
                (
                    result.match_id,
                    result.player_id,
                    result.ended_at,
                    result.playlist,
                    result.outcome,
                ),
            )

    def history(self, player_id: str, limit: int = 100) -> list[sqlite3.Row]:
        """Return the most recently observed matches for one player."""
        return self.connection.execute(
            """
            SELECT ended_at, playlist, outcome FROM matches
            WHERE player_id = ? ORDER BY ended_at DESC, rowid DESC LIMIT ?
            """,
            (player_id, limit),
        ).fetchall()

    def sessions(self, player_id: str) -> list[str]:
        """Derive session starts from gaps of at least one hour between results."""
        rows = self.connection.execute(
            "SELECT ended_at FROM matches WHERE player_id = ? ORDER BY ended_at",
            (player_id,),
        ).fetchall()
        starts: list[str] = []
        previous: datetime | None = None
        for row in rows:
            timestamp = datetime.fromisoformat(row["ended_at"])
            if previous is None or timestamp - previous >= timedelta(hours=1):
                starts.append(row["ended_at"])
            previous = timestamp
        return starts

    def filtered_history(
        self,
        player_id: str,
        session_start: str | None,
        playlist: int | None,
        filter_playlist: bool = False,
    ) -> list[sqlite3.Row]:
        """Return all matching results so counts and displayed history share a scope."""
        conditions = ["player_id = ?"]
        parameters: list[str | int | None] = [player_id]
        if session_start is not None:
            conditions.append("ended_at >= ?")
            parameters.append(session_start)
            starts = self.sessions(player_id)
            later = [start for start in starts if start > session_start]
            if len(later) > 0:
                conditions.append("ended_at < ?")
                parameters.append(later[0])
        if filter_playlist:
            conditions.append("playlist IS ?")
            parameters.append(playlist)
        return self.connection.execute(
            "SELECT ended_at, playlist, outcome FROM matches WHERE "
            + " AND ".join(conditions)
            + " ORDER BY ended_at DESC, rowid DESC",
            parameters,
        ).fetchall()

    def summary(self, player_id: str) -> Summary:
        """Aggregate the entire history without the display row limit."""
        rows = self.connection.execute(
            "SELECT outcome, COUNT(*) AS count FROM matches WHERE player_id = ? GROUP BY outcome",
            (player_id,),
        ).fetchall()
        counts = {row["outcome"]: row["count"] for row in rows}
        return Summary(counts.get("win", 0), counts.get("loss", 0), counts.get("unknown", 0))

    def setting(self, key: str) -> str:
        """Read a setting, returning an empty string if it has not been saved."""
        row = self.connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return ""
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        """Persist a local preference."""
        with self.connection:
            self.connection.execute(
                "INSERT INTO settings VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = ?",
                (key, value, value),
            )

    def close(self) -> None:
        """Release the database connection."""
        self.connection.close()
