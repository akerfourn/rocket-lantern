"""Idempotent SQLite migration and normalized match detail persistence."""

import sqlite3

from rocket_lantern.match_data import MatchSnapshot


def migrate(connection: sqlite3.Connection) -> None:
    """Add detail tables and link legacy results without losing existing history."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > 5:
        raise sqlite3.DatabaseError("Database schema is newer than this application")
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
                    actor_id, secondary_id, team, speed, round_seconds, x, y, z
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
