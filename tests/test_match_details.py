"""Structured match collection, migration and relational storage contracts."""

import sqlite3
from pathlib import Path

from rocket_lantern.match_data import MatchCollector
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult

TIME = "2026-10-03T18:00:00+00:00"


def state(goals: int = 1) -> dict[str, object]:
    """Build a synthetic snapshot with an omitted counter and explicit zero."""
    return {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": "match",
            "Game": {
                "PlaylistId": 11,
                "Arena": "Stadium_P",
                "TimeSeconds": 120,
                "bOvertime": False,
                "bReplay": False,
                "Teams": [{"TeamNum": 0, "Score": goals}, {"TeamNum": 1, "Score": 0}],
            },
            "Players": [
                {
                    "PrimaryId": "Epic|one|0",
                    "Name": "One",
                    "TeamNum": 0,
                    "Shortcut": 1,
                    "Goals": goals,
                    "Shots": 0,
                }
            ],
        },
    }


def goal() -> dict[str, object]:
    """Build an important event linked via its spectator shortcut."""
    return {
        "Event": "GoalScored",
        "Data": {
            "MatchGuid": "match",
            "Scorer": {"Name": "One", "Shortcut": 1, "TeamNum": 0},
            "GoalTime": 12.5,
            "GoalSpeed": 1800,
            "ImpactLocation": {"X": 0, "Y": -5000, "Z": 100},
        },
    }


def test_details_should_link_players_and_deduplicate_when_goal_is_repeated() -> None:
    collector = MatchCollector()
    collector.observe(state(), TIME)
    collector.observe(goal(), TIME)
    snapshot = collector.observe(goal(), "2026-10-03T18:00:01+00:00")
    assert snapshot is not None
    store = MatchStore(":memory:")
    try:
        store.save_details(snapshot)
        store.save_details(snapshot)
        store.save(MatchResult("match", "Epic|one|0", TIME, 11, "win"))
        player = store.participants("match")[0]
        event = store.events("match")[0]
        assert player["goals"] == 1
        assert player["shots"] == 0
        assert player["saves"] is None
        assert event["actor_id"] == player["player_id"]
        assert event["secondary_id"] is None
        assert event["speed"] == 1800
        assert event["round_seconds"] == 12.5
        assert len(store.events("match")) == 1
        assert store.connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        store.close()


def test_collector_should_retain_departed_player_and_accept_post_end_state() -> None:
    collector = MatchCollector()
    collector.observe(state(), TIME)
    collector.observe(
        {
            "Event": "MatchEnded",
            "Data": {
                "MatchGuid": "match",
                "WinnerTeamNum": 0,
            },
        },
        TIME,
    )
    snapshot = collector.observe(state(2), TIME)
    assert snapshot is not None
    assert snapshot.players["Epic|one|0"].goals == 2
    assert snapshot.final_observed
    collector.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "match",
                "Game": {},
                "Players": [],
            },
        },
        TIME,
    )
    assert len(snapshot.players) == 1


def test_collector_should_ignore_replay_stats_and_events_when_goal_replay_is_active() -> None:
    collector = MatchCollector()
    snapshot = collector.observe(state(), TIME)
    collector.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "match",
                "Game": {"bReplay": True},
                "Players": [],
            },
        },
        TIME,
    )
    collector.observe(goal(), TIME)
    assert snapshot is not None
    assert len(snapshot.events) == 0
    assert snapshot.players["Epic|one|0"].goals == 1


def test_event_should_leave_actor_unlinked_when_shortcut_identity_is_not_certain() -> None:
    collector = MatchCollector()
    collector.observe(state(), TIME)
    collector.observe(
        {
            "Event": "StatfeedEvent",
            "Data": {
                "MatchGuid": "match",
                "EventName": "Demolish",
                "MainTarget": {"Name": "Other", "Shortcut": 1, "TeamNum": 0},
            },
        },
        TIME,
    )
    event = next(iter(collector.snapshots["match"].events.values()))
    assert event.kind == "Stat:Demolish"
    assert event.actor is None


def test_migration_should_keep_legacy_history_when_database_is_reopened(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("""
        CREATE TABLE matches (
            match_id TEXT NOT NULL, player_id TEXT NOT NULL, ended_at TEXT NOT NULL,
            playlist INTEGER, outcome TEXT NOT NULL, PRIMARY KEY (match_id, player_id)
        )
    """)
    connection.execute(
        "INSERT INTO matches VALUES (?, ?, ?, ?, ?)",
        (
            "old",
            "test",
            TIME,
            11,
            "win",
        ),
    )
    connection.commit()
    connection.close()
    for _ in range(2):
        store = MatchStore(path)
        try:
            assert store.summary("test").wins == 1
            row = store.connection.execute("SELECT detail_id, player_ref FROM matches").fetchone()
            assert row["detail_id"] is not None
            assert row["player_ref"] is not None
            assert store.participants("old") == []
            assert store.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            store.close()


def test_storage_should_preserve_final_stats_when_partial_reconnection_arrives() -> None:
    collector = MatchCollector()
    collector.observe(state(2), TIME)
    collector.observe(
        {
            "Event": "MatchEnded",
            "Data": {
                "MatchGuid": "match",
                "WinnerTeamNum": 0,
            },
        },
        TIME,
    )
    final = collector.observe(state(2), TIME)
    partial = MatchCollector().observe(state(1), TIME)
    assert final is not None and partial is not None
    store = MatchStore(":memory:")
    try:
        store.save_details(final)
        store.save_details(partial)
        assert store.participants("match")[0]["goals"] == 2
        assert store.detail("match")["blue_score"] == 2
        assert store.detail("match")["winner"] == 0
    finally:
        store.close()
