"""Idempotent SQLite migration and normalized match detail persistence."""

import json
import sqlite3

from rocket_lantern.match_data import MatchSnapshot
from rocket_lantern.storage_errors import NewerDatabaseSchemaError

SCHEMA_VERSION = 6


def check_schema_version(connection: sqlite3.Connection) -> int:
    """Reject a newer schema before callers create or migrate any tables."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise NewerDatabaseSchemaError(version, SCHEMA_VERSION)
    return version


def migrate(connection: sqlite3.Connection) -> None:
    """Add detail tables and link legacy results without losing existing history."""
    version = check_schema_version(connection)
    if version >= 1:
        return
    connection.executescript(
        """
        BEGIN;
        CREATE TABLE match_details (
            id INTEGER PRIMARY KEY,
            guid TEXT NOT NULL UNIQUE,
            observed_at TEXT,
            playlist INTEGER,
            arena TEXT,
            blue_score INTEGER,
            orange_score INTEGER,
            overtime INTEGER,
            winner INTEGER,
            final_observed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE players (
            id INTEGER PRIMARY KEY,
            primary_id TEXT NOT NULL UNIQUE
        );
        CREATE TABLE match_players (
            match_id INTEGER NOT NULL REFERENCES match_details(id),
            player_id INTEGER NOT NULL REFERENCES players(id),
            name TEXT NOT NULL,
            team INTEGER NOT NULL,
            score INTEGER, goals INTEGER, shots INTEGER, assists INTEGER,
            saves INTEGER, touches INTEGER, car_touches INTEGER, demos INTEGER,
            PRIMARY KEY (match_id, player_id)
        );
        CREATE TABLE match_events (
            id INTEGER PRIMARY KEY,
            match_id INTEGER NOT NULL REFERENCES match_details(id),
            fingerprint TEXT NOT NULL,
            kind TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            time_seconds INTEGER,
            overtime INTEGER,
            actor_id INTEGER REFERENCES players(id),
            secondary_id INTEGER REFERENCES players(id),
            team INTEGER,
            speed REAL,
            round_seconds REAL,
            x REAL, y REAL, z REAL,
            UNIQUE (match_id, fingerprint)
        );
        ALTER TABLE matches ADD COLUMN detail_id INTEGER REFERENCES match_details(id);
        ALTER TABLE matches ADD COLUMN player_ref INTEGER REFERENCES players(id);
        INSERT INTO match_details (guid) SELECT DISTINCT match_id FROM matches;
        INSERT INTO players (primary_id) SELECT DISTINCT player_id FROM matches;
        UPDATE matches SET
            detail_id = (SELECT id FROM match_details WHERE guid = matches.match_id),
            player_ref = (SELECT id FROM players WHERE primary_id = matches.player_id);
        PRAGMA user_version = 1;
        COMMIT;
        """
    )


def migrate_events(connection: sqlite3.Connection) -> None:
    """Extend existing event rows without replacing their IDs or coordinates."""
    if connection.execute("PRAGMA user_version").fetchone()[0] >= 6:
        return
    with connection:
        connection.execute("BEGIN")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(match_events)")}
        additions = {
            "source_event": "TEXT NOT NULL DEFAULT ''",
            "origin": "TEXT NOT NULL DEFAULT 'api'",
            "position_subject": "TEXT",
            "details_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE match_events ADD COLUMN {name} {definition}")
        connection.execute(
            """UPDATE match_events SET
                source_event = CASE WHEN kind LIKE 'Stat:%' THEN 'StatfeedEvent' ELSE kind END,
                position_subject = CASE
                    WHEN kind IN ('GoalScored', 'CrossbarHit') THEN 'ball' END
                WHERE source_event = ''"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS match_event_players (
                event_id INTEGER NOT NULL REFERENCES match_events(id),
                position INTEGER NOT NULL,
                role TEXT NOT NULL,
                player_id INTEGER REFERENCES players(id),
                name TEXT, team INTEGER, shortcut INTEGER,
                PRIMARY KEY (event_id, position)
            )"""
        )
        connection.execute("PRAGMA user_version = 6")


def player_key(connection: sqlite3.Connection, primary_id: str) -> int:
    """Resolve a permanent participant identity to its database key."""
    connection.execute("INSERT OR IGNORE INTO players (primary_id) VALUES (?)", (primary_id,))
    return connection.execute(
        "SELECT id FROM players WHERE primary_id = ?", (primary_id,)
    ).fetchone()[0]


def match_key(connection: sqlite3.Connection, guid: str) -> int:
    """Resolve the game's match GUID to a stable internal key."""
    connection.execute("INSERT OR IGNORE INTO match_details (guid) VALUES (?)", (guid,))
    return connection.execute("SELECT id FROM match_details WHERE guid = ?", (guid,)).fetchone()[0]


def save_snapshot(connection: sqlite3.Connection, snapshot: MatchSnapshot) -> None:
    """Merge known values and deduplicate events in one transaction."""
    with connection:
        match_id = match_key(connection, snapshot.guid)
        current = connection.execute(
            "SELECT final_observed FROM match_details WHERE id = ?", (match_id,)
        ).fetchone()
        # A reconnect with a partial state must not overwrite a final snapshot.
        if current[0] == 1 and not snapshot.final_observed:
            _save_events(connection, snapshot, match_id)
            return
        connection.execute(
            """
            UPDATE match_details SET
                observed_at = ?, playlist = COALESCE(?, playlist),
                arena = COALESCE(?, arena), blue_score = COALESCE(?, blue_score),
                orange_score = COALESCE(?, orange_score), overtime = COALESCE(?, overtime),
                winner = COALESCE(?, winner), final_observed = MAX(final_observed, ?)
            WHERE id = ?
            """,
            (
                snapshot.observed_at,
                snapshot.playlist,
                snapshot.arena,
                snapshot.blue_score,
                snapshot.orange_score,
                snapshot.overtime,
                snapshot.winner,
                snapshot.final_observed,
                match_id,
            ),
        )
        for player in snapshot.players.values():
            player_id = player_key(connection, player.primary_id)
            connection.execute(
                """
                INSERT INTO match_players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (match_id, player_id) DO UPDATE SET
                    name = excluded.name, team = excluded.team,
                    score = COALESCE(excluded.score, score),
                    goals = COALESCE(excluded.goals, goals),
                    shots = COALESCE(excluded.shots, shots),
                    assists = COALESCE(excluded.assists, assists),
                    saves = COALESCE(excluded.saves, saves),
                    touches = COALESCE(excluded.touches, touches),
                    car_touches = COALESCE(excluded.car_touches, car_touches),
                    demos = COALESCE(excluded.demos, demos)
                """,
                (
                    match_id,
                    player_id,
                    player.name,
                    player.team,
                    player.score,
                    player.goals,
                    player.shots,
                    player.assists,
                    player.saves,
                    player.touches,
                    player.car_touches,
                    player.demos,
                ),
            )
        _save_events(connection, snapshot, match_id)


def _save_events(connection: sqlite3.Connection, snapshot: MatchSnapshot, match_id: int) -> None:
    """Insert pending occurrences and every explicitly identified participant."""
    for event in snapshot.events.values():
        actor_id = None
        secondary_id = None
        if event.actor is not None:
            actor_id = player_key(connection, event.actor)
        if event.secondary is not None:
            secondary_id = player_key(connection, event.secondary)
        connection.execute(
            """
                INSERT OR IGNORE INTO match_events (
                    match_id, fingerprint, kind, observed_at, time_seconds, overtime,
                    actor_id, secondary_id, team, speed, round_seconds, x, y, z,
                    source_event, origin, position_subject, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
            (
                match_id,
                event.fingerprint,
                event.kind,
                event.observed_at,
                event.time_seconds,
                event.overtime,
                actor_id,
                secondary_id,
                event.team,
                event.speed,
                event.round_seconds,
                event.x,
                event.y,
                event.z,
                event.source_event or event.kind,
                event.origin,
                event.position_subject,
                json.dumps(event.details, sort_keys=True, allow_nan=False),
            ),
        )
        event_id = connection.execute(
            "SELECT id FROM match_events WHERE match_id = ? AND fingerprint = ?",
            (match_id, event.fingerprint),
        ).fetchone()[0]
        for position, participant in enumerate(event.participants):
            participant_id = None
            if participant.primary_id is not None:
                participant_id = player_key(connection, participant.primary_id)
            connection.execute(
                """INSERT OR IGNORE INTO match_event_players
                       (event_id, position, role, player_id, name, team, shortcut)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    position,
                    participant.role,
                    participant_id,
                    participant.name,
                    participant.team,
                    participant.shortcut,
                ),
            )
