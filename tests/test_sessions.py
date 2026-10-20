"""Stable session membership, explicit splits and legacy database migration."""

import sqlite3
from pathlib import Path

import pytest

from rocket_lantern.match_repository import migrate
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult


def test_sessions_should_keep_manual_boundary_when_matches_are_minutes_apart(
    tmp_path: Path,
) -> None:
    store = MatchStore(tmp_path / "sessions.sqlite3")
    try:
        store.save(MatchResult("before", "player", "2026-10-04T12:00:00+00:00", 11, "win"))
        first = store.sessions("player")[0]["id"]
        second = store.start_session("player", "2026-10-04T12:01:00+00:00")
        store.save(MatchResult("after", "player", "2026-10-04T12:02:00+00:00", 13, "loss"))

        assert first != second
        first_matches = store.filtered_history("player", first, None)
        second_matches = store.filtered_history("player", second, None)
        assert [row["match_id"] for row in first_matches] == ["before"]
        assert [row["match_id"] for row in second_matches] == ["after"]
        assert store.current_session("player", "2026-10-04T12:03:00+00:00") == second
        assert store.filtered_history("another-player", second, None) == []
    finally:
        store.close()


def test_sessions_should_keep_empty_session_when_database_is_reopened(tmp_path: Path) -> None:
    path = tmp_path / "sessions.sqlite3"
    store = MatchStore(path)
    session_id = store.start_session("player", "2026-10-04T12:00:00+00:00")
    store.close()

    reopened = MatchStore(path)
    try:
        assert reopened.current_session("player", "2026-10-04T12:10:00+00:00") == session_id
        assert reopened.filtered_history("player", session_id, None) == []
        reopened.save(MatchResult("new", "player", "2026-10-04T12:15:00+00:00", 11, "win"))
        assert len(reopened.sessions("player")) == 1
        assert len(reopened.filtered_history("player", session_id, None)) == 1
    finally:
        reopened.close()


def test_sessions_should_not_move_match_when_late_result_corrects_unknown(tmp_path: Path) -> None:
    store = MatchStore(tmp_path / "sessions.sqlite3")
    try:
        store.save(MatchResult("one", "player", "2026-10-04T12:00:00+00:00", 11, "unknown"))
        first = store.sessions("player")[0]["id"]
        second = store.start_session("player", "2026-10-04T12:01:00+00:00")

        store.save(MatchResult("one", "player", "2026-10-04T14:00:00+00:00", 11, "win"))

        assert store.filtered_history("player", first, None)[0]["outcome"] == "win"
        assert store.filtered_history("player", second, None) == []
        assert len(store.sessions("player")) == 2
    finally:
        store.close()


def test_sessions_should_expire_empty_manual_session_when_one_hour_passes(tmp_path: Path) -> None:
    store = MatchStore(tmp_path / "sessions.sqlite3")
    try:
        first = store.start_session("player", "2026-10-04T12:00:00+00:00")
        assert store.current_session("player", "2026-10-04T12:59:59+00:00") == first
        assert store.current_session("player", "2026-10-04T13:00:00+00:00") is None
        assert len(store.sessions("player")) == 1, "Reading must not create empty sessions"

        store.save(MatchResult("one", "player", "2026-10-04T13:00:00+00:00", 11, "win"))

        assert len(store.sessions("player")) == 2
        assert store.filtered_history("player", first, None) == []
    finally:
        store.close()


def create_legacy_database(path: Path) -> None:
    """Create the previous schema with interleaved players and a one-hour gap."""
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE matches (
            match_id TEXT, player_id TEXT, ended_at TEXT, playlist INTEGER, outcome TEXT,
            PRIMARY KEY (match_id, player_id)
        )
        """
    )
    connection.executemany(
        "INSERT INTO matches VALUES (?, ?, ?, ?, ?)",
        [
            ("one", "player", "2026-10-04T12:00:00+00:00", 11, "win"),
            ("two", "player", "2026-10-04T12:10:00+00:00", 13, "loss"),
            ("three", "player", "2026-10-04T13:10:00+00:00", 11, "unknown"),
            ("one", "other", "2026-10-04T12:00:00+00:00", 11, "loss"),
        ],
    )
    connection.commit()
    migrate(connection)
    connection.close()


def test_migration_should_preserve_groups_and_ids_when_legacy_database_is_reopened(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    create_legacy_database(path)
    store = MatchStore(path)
    sessions = [dict(row) for row in store.sessions("player")]
    try:
        assert len(sessions) == 2
        assert len(store.filtered_history("player", sessions[0]["id"], None)) == 2
        assert len(store.filtered_history("player", sessions[1]["id"], None)) == 1
        assert len(store.sessions("other")) == 1
        assert store.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 5
    finally:
        store.close()

    reopened = MatchStore(path)
    try:
        assert [dict(row) for row in reopened.sessions("player")] == sessions
        assert reopened.summary("player").wins == 1
        assert reopened.summary("player").losses == 1
        assert reopened.summary("player").unknown == 1
    finally:
        reopened.close()


def test_sessions_should_reject_manual_creation_when_no_player_is_selected(tmp_path: Path) -> None:
    store = MatchStore(tmp_path / "sessions.sqlite3")
    try:
        with pytest.raises(ValueError, match="Sélectionne un joueur"):
            store.start_session("", "2026-10-04T12:00:00+00:00")
        assert store.sessions("") == []
    finally:
        store.close()
