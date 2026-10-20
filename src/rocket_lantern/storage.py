"""Small SQLite repository; each match is counted once per selected player."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from rocket_lantern.evaluation_repository import (
    migrate_evaluations,
    read_evaluation,
    save_evaluation,
)
from rocket_lantern.label_repository import LabelRepository, migrate_labels
from rocket_lantern.match_data import MatchSnapshot
from rocket_lantern.match_repository import match_key, migrate, player_key, save_snapshot
from rocket_lantern.session_repository import (
    assign_session,
    create_session,
    current_session,
    migrate_sessions,
)
from rocket_lantern.tracker import MatchResult


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
        try:
            self._initialize_schema()
        except sqlite3.Error:
            self.connection.close()
            raise

    def _initialize_schema(self) -> None:
        """Prepare the schema before exposing a usable connection."""
        self.connection.execute("PRAGMA foreign_keys = ON")
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
        migrate(self.connection)
        migrate_sessions(self.connection)
        migrate_evaluations(self.connection)
        migrate_labels(self.connection)
        self.labels = LabelRepository(self.connection)

    def save(self, result: MatchResult) -> None:
        """Allow a confirmed result to replace an unknown, never the reverse."""
        with self.connection:
            detail_id = match_key(self.connection, result.match_id)
            player_ref = player_key(self.connection, result.player_id)
            session_id = assign_session(
                self.connection, result.match_id, result.player_id, result.ended_at
            )
            self.connection.execute(
                """
                INSERT INTO matches (
                    match_id, player_id, ended_at, playlist, outcome, detail_id, player_ref,
                    session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                    detail_id,
                    player_ref,
                    session_id,
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

    def sessions(self, player_id: str) -> list[sqlite3.Row]:
        """Read stable sessions, including manually created sessions without results."""
        return self.connection.execute(
            "SELECT id, started_at FROM sessions WHERE player_id = ? ORDER BY id",
            (player_id,),
        ).fetchall()

    def start_session(self, player_id: str, started_at: str) -> int:
        """Force a new session for subsequent results without moving old matches."""
        if player_id == "":
            raise ValueError("Sélectionne un joueur avant de créer une session.")
        with self.connection:
            return create_session(self.connection, player_id, started_at)

    def session_detail(self, player_id: str, session_id: int) -> sqlite3.Row | None:
        """Read session metadata only for its owning player."""
        return self.connection.execute(
            "SELECT id, started_at, last_activity_at FROM sessions WHERE id = ? AND player_id = ?",
            (session_id, player_id),
        ).fetchone()

    def session_matches(self, player_id: str, session_id: int) -> list[sqlite3.Row]:
        """Read all session matches, preserving missing details and player statistics."""
        return list(reversed(self.filtered_history(player_id, session_id, None)))

    def current_session(self, player_id: str, observed_at: str) -> int | None:
        """Return the active session ID without creating a session during a read."""
        return current_session(self.connection, player_id, observed_at)

    def filtered_history(
        self,
        player_id: str,
        session_id: int | None,
        playlist: int | None,
        filter_playlist: bool = False,
    ) -> list[sqlite3.Row]:
        """Read matching results and player stats without limiting aggregate coverage."""
        conditions = ["m.player_id = ?"]
        parameters: list[str | int | None] = [player_id]
        if session_id is not None:
            conditions.append("m.session_id = ?")
            parameters.append(session_id)
        if filter_playlist:
            conditions.append("m.playlist IS ?")
            parameters.append(playlist)
        return self.connection.execute(
            """
            SELECT m.match_id, m.ended_at, m.playlist, m.outcome,
                   d.arena, d.blue_score, d.orange_score, d.overtime, d.final_observed,
                   d.observed_at, p.team, p.score, p.goals, p.shots, p.assists, p.saves,
                   p.touches, p.car_touches, p.demos,
                   COALESCE(e.label_id, 'not_evaluated') AS evaluation
            FROM matches m
            LEFT JOIN match_details d ON d.id = m.detail_id
            LEFT JOIN match_players p ON p.match_id = m.detail_id AND p.player_id = m.player_ref
            LEFT JOIN match_labels e ON e.match_id = m.detail_id AND e.list_id = 'smurfing'
            WHERE """
            + " AND ".join(conditions)
            + " ORDER BY m.ended_at DESC, m.rowid DESC",
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

    def known_players(self) -> list[sqlite3.Row]:
        """Read one identity per player with its latest saved match name, not full matches."""
        return self.connection.execute(
            """
            SELECT primary_id, COALESCE(NULLIF(name, ''), primary_id) AS name
            FROM (
                SELECT p.primary_id, mp.name,
                       ROW_NUMBER() OVER (
                           PARTITION BY p.id ORDER BY d.observed_at DESC, d.id DESC
                       ) AS rank
                FROM players p
                LEFT JOIN match_players mp ON mp.player_id = p.id
                LEFT JOIN match_details d ON d.id = mp.match_id
            )
            WHERE rank = 1
            ORDER BY name COLLATE NOCASE, primary_id
            """
        ).fetchall()

    def set_settings(self, values: dict[str, str]) -> None:
        """Save related preferences atomically."""
        with self.connection:
            self.connection.executemany(
                "INSERT INTO settings VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                values.items(),
            )

    def evaluation(self, guid: str) -> str:
        """Read a match-level assessment independent of player or history filters."""
        return read_evaluation(self.connection, guid)

    def set_evaluation(self, guid: str, value: str, updated_at: str) -> None:
        """Save a manual assessment without touching outcome, counters or sessions."""
        save_evaluation(self.connection, guid, value, updated_at)

    def close(self) -> None:
        """Release the database connection."""
        self.connection.close()

    def save_details(self, snapshot: MatchSnapshot) -> None:
        """Persist a structured match observation without raw API messages."""
        save_snapshot(self.connection, snapshot)

    def detail(self, guid: str) -> sqlite3.Row | None:
        """Read match metadata by its API GUID."""
        return self.connection.execute(
            "SELECT * FROM match_details WHERE guid = ?", (guid,)
        ).fetchone()

    def participants(self, guid: str) -> list[sqlite3.Row]:
        """Read per-match identities and counters, including departed participants."""
        return self.connection.execute(
            """
            SELECT mp.*, p.primary_id FROM match_players mp
            JOIN players p ON p.id = mp.player_id
            JOIN match_details m ON m.id = mp.match_id
            WHERE m.guid = ? ORDER BY mp.team, mp.score DESC, mp.player_id
            """,
            (guid,),
        ).fetchall()

    def player_team(self, guid: str, primary_id: str) -> int | None:
        """Read the selected player's team in this match, never from another match."""
        row = self.connection.execute(
            """
            SELECT mp.team FROM match_players mp
            JOIN players p ON p.id = mp.player_id
            JOIN match_details m ON m.id = mp.match_id
            WHERE m.guid = ? AND p.primary_id = ?
            """,
            (guid, primary_id),
        ).fetchone()
        if row is None:
            return None
        return row["team"]

    def events(self, guid: str) -> list[sqlite3.Row]:
        """Read important events with names scoped to this match."""
        return self.connection.execute(
            """
            SELECT e.*, a.name AS actor_name, s.name AS secondary_name
            FROM match_events e JOIN match_details m ON m.id = e.match_id
            LEFT JOIN match_players a ON a.match_id = e.match_id AND a.player_id = e.actor_id
            LEFT JOIN match_players s ON s.match_id = e.match_id AND s.player_id = e.secondary_id
            WHERE m.guid = ? ORDER BY e.observed_at, e.id
            """,
            (guid,),
        ).fetchall()
