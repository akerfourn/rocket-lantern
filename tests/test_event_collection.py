"""Compact event timelines, identity links and lossless schema upgrades."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from rocket_lantern.match_data import MatchCollector, MatchSnapshot
from rocket_lantern.match_repository import migrate_events
from rocket_lantern.storage import MatchStore

TIME = "2026-10-22T18:00:00.000000+00:00"
LATER = "2026-10-22T18:00:00.100000+00:00"
PLAYER = {"PrimaryId": "Epic|one|0", "Name": "One", "TeamNum": 0, "Shortcut": 1}
OTHER = {"PrimaryId": "Epic|two|0", "Name": "Two", "TeamNum": 1, "Shortcut": 2}


def update(
    collector: MatchCollector,
    *,
    flags: dict[str, object] | None = None,
    replay: bool = False,
    at: str = TIME,
) -> MatchSnapshot:
    players = [dict(PLAYER), dict(OTHER)]
    if flags is not None:
        players[0].update(flags)
    snapshot = collector.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "match",
                "Players": players,
                "Game": {"TimeSeconds": 120, "bOvertime": False, "bReplay": replay},
            },
        },
        at,
    )
    assert snapshot is not None
    return snapshot


def emit(
    collector: MatchCollector,
    name: str,
    data: dict[str, object] | None = None,
    at: str = TIME,
) -> MatchSnapshot:
    payload: dict[str, object] = {"MatchGuid": "match"}
    if data is not None:
        payload.update(data)
    snapshot = collector.observe({"Event": name, "Data": payload}, at)
    assert snapshot is not None
    return snapshot


@pytest.fixture
def store() -> Iterator[MatchStore]:
    repository = MatchStore(":memory:")
    yield repository
    repository.close()


@pytest.mark.parametrize(
    "kind",
    [
        "MatchCreated",
        "MatchInitialized",
        "CountdownBegin",
        "RoundStarted",
        "ClockUpdatedSeconds",
        "MatchPaused",
        "MatchUnpaused",
        "MatchEnded",
        "PodiumStart",
        "MatchDestroyed",
        "GoalReplayStart",
        "GoalReplayWillEnd",
        "GoalReplayEnd",
        "FutureEvent",
    ],
)
def test_collector_should_store_discrete_notifications_with_clock_context(
    store: MatchStore,
    kind: str,
) -> None:
    collector = MatchCollector()
    update(collector)
    snapshot = emit(collector, kind, at=LATER)

    store.save_details(snapshot)

    row = store.events("match")[0]
    assert row["source_event"] == kind
    assert row["origin"] == "api"
    assert row["observed_at"] == LATER
    assert row["time_seconds"] == 120
    assert row["overtime"] == 0
    assert (row["x"], row["y"], row["z"]) == (None, None, None)


def test_ball_hit_should_store_position_speeds_and_all_hitters(store: MatchStore) -> None:
    collector = MatchCollector()
    update(collector)
    snapshot = emit(
        collector,
        "BallHit",
        {
            "Players": [
                {"Name": "One", "TeamNum": 0, "Shortcut": 1},
                {"Name": "Two", "TeamNum": 1, "Shortcut": 2},
            ],
            "Ball": {
                "Location": {"X": -500, "Y": 0, "Z": 350},
                "PreHitSpeed": 0,
                "PostHitSpeed": 1500,
            },
            "Unused": {"Raw": "must not be retained"},
        },
    )

    store.save_details(snapshot)
    store.save_details(snapshot)

    rows = store.events("match")
    assert len(rows) == 1
    row = rows[0]
    assert (row["x"], row["y"], row["z"]) == (-500, 0, 350)
    assert row["position_subject"] == "ball"
    assert row["speed"] == 1500
    assert json.loads(row["details_json"]) == {"PreHitSpeed": 0, "PostHitSpeed": 1500}
    participants = store.event_participants(row["id"])
    assert [item["primary_id"] for item in participants] == [
        PLAYER["PrimaryId"],
        OTHER["PrimaryId"],
    ]
    assert [item["role"] for item in participants] == ["hitter", "hitter"]
    assert store.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_collector_should_preserve_identical_contacts_within_one_clock_tick(
    store: MatchStore,
) -> None:
    collector = MatchCollector()
    update(collector)
    data = {"Players": [PLAYER], "Ball": {"PostHitSpeed": 1000}}
    emit(collector, "BallHit", data)
    snapshot = emit(collector, "BallHit", data)
    store.save_details(snapshot)
    snapshot.events.clear()
    snapshot = emit(collector, "BallHit", data, LATER)
    store.save_details(snapshot)

    rows = store.events("match")
    assert len(rows) == 3
    assert len({row["fingerprint"] for row in rows}) == 3
    assert {row["time_seconds"] for row in rows} == {120}


def test_boost_pickup_should_store_collector_and_pickup_not_car_position(store: MatchStore) -> None:
    collector = MatchCollector()
    update(collector)
    snapshot = emit(
        collector,
        "BoostPickup",
        {
            "Player": PLAYER,
            "Location": {"X": 0, "Y": 3000, "Z": 73},
            "BoostAmount": 12,
            "BoostType": "BoostType_Pad",
            "bReplay": False,
        },
    )
    store.save_details(snapshot)

    row = store.events("match")[0]
    assert row["position_subject"] == "boost_pickup"
    assert json.loads(row["details_json"]) == {"BoostAmount": 12, "BoostType": "BoostType_Pad"}
    assert store.event_participants(row["id"])[0]["role"] == "collector"


def test_goal_should_keep_last_touch_separate_from_absent_assister(store: MatchStore) -> None:
    collector = MatchCollector()
    update(collector)
    snapshot = emit(
        collector,
        "GoalScored",
        {
            "Scorer": PLAYER,
            "BallLastTouch": {"Player": OTHER, "Speed": 900},
            "GoalSpeed": 800,
            "GoalTime": 15.5,
        },
    )
    store.save_details(snapshot)
    row = store.events("match")[0]

    assert row["actor_id"] is not None
    assert row["secondary_id"] is None
    assert json.loads(row["details_json"]) == {"LastTouchSpeed": 900}
    assert [p["role"] for p in store.event_participants(row["id"])] == ["scorer", "last_touch"]


def test_crossbar_should_keep_impact_force_and_last_touch_speed(store: MatchStore) -> None:
    collector = MatchCollector()
    update(collector)
    snapshot = emit(
        collector,
        "CrossbarHit",
        {
            "BallLastTouch": {"Player": PLAYER, "Speed": 900},
            "BallSpeed": 850,
            "ImpactForce": 120,
            "BallLocation": {"X": 0, "Y": 5000, "Z": 600},
        },
    )
    store.save_details(snapshot)
    row = store.events("match")[0]

    assert row["actor_id"] is not None
    assert json.loads(row["details_json"]) == {"LastTouchSpeed": 900, "ImpactForce": 120}
    assert (row["x"], row["y"], row["z"]) == (0, 5000, 600)


@pytest.mark.parametrize("kind", ["PlayerJoined", "PlayerLeft"])
def test_player_events_should_link_explicit_ids_before_any_snapshot(
    store: MatchStore,
    kind: str,
) -> None:
    snapshot = emit(MatchCollector(), kind, {"PrimaryId": "Epic|new|0", "PlayerName": "New"})
    store.save_details(snapshot)

    row = store.events("match")[0]
    participant = store.event_participants(row["id"])[0]
    assert participant["primary_id"] == "Epic|new|0"
    assert participant["name"] == "New"
    assert row["time_seconds"] is None
    assert store.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0


def test_event_should_preserve_unresolved_participant_without_guessing_by_name(
    store: MatchStore,
) -> None:
    collector = MatchCollector()
    update(collector)
    snapshot = emit(
        collector,
        "BallHit",
        {
            "Players": [
                {"Name": "One", "TeamNum": 1, "Shortcut": 1},
            ]
        },
    )
    store.save_details(snapshot)

    row = store.events("match")[0]
    participant = store.event_participants(row["id"])[0]
    assert row["actor_id"] is None
    assert participant["player_id"] is None
    assert (participant["name"], participant["team"], participant["shortcut"]) == ("One", 1, 1)


def test_state_should_store_only_changes_and_mark_missing_values_unknown(store: MatchStore) -> None:
    collector = MatchCollector()
    snapshot = update(collector, flags={"bOnGround": True, "bBoosting": False})
    for _ in range(100):
        update(collector, flags={"bOnGround": True, "bBoosting": False})
    assert len(snapshot.events) == 2

    update(collector, flags={"bOnGround": False, "bBoosting": False}, at=LATER)
    update(collector, flags={"bBoosting": False}, at=LATER)
    update(collector, flags={"bBoosting": False}, at=LATER)
    store.save_details(snapshot)

    ground = [row for row in store.events("match") if row["kind"] == "PlayerState:bOnGround"]
    assert [json.loads(row["details_json"]) for row in ground] == [
        {"previous": None, "value": True},
        {"previous": True, "value": False},
        {"previous": False, "value": None},
    ]
    assert all(row["origin"] == "state" for row in ground)
    assert all(row["x"] is None and row["speed"] is None for row in ground)


def test_state_should_ignore_invalid_booleans_without_creating_false_airtime() -> None:
    snapshot = update(MatchCollector(), flags={"bOnGround": 0, "bOnWall": "false"})
    assert not snapshot.events


def test_collector_should_ignore_replayed_actions_but_keep_replay_boundaries(
    store: MatchStore,
) -> None:
    collector = MatchCollector()
    snapshot = update(collector, flags={"bOnGround": True})
    emit(collector, "GoalReplayStart")
    emit(collector, "BallHit", {"Players": [PLAYER]})
    emit(collector, "BoostPickup", {"Player": PLAYER, "bReplay": True})
    emit(collector, "GoalReplayWillEnd")
    emit(collector, "GoalReplayEnd", at=LATER)
    update(collector, flags={"bOnGround": False}, at=LATER)
    store.save_details(snapshot)

    kinds = [row["kind"] for row in store.events("match")]
    assert "BallHit" not in kinds
    assert "BoostPickup" not in kinds
    assert "GoalReplayStart" in kinds and "GoalReplayWillEnd" in kinds and "GoalReplayEnd" in kinds
    states = [row for row in store.events("match") if row["origin"] == "state"]
    assert [json.loads(row["details_json"])["value"] for row in states] == [True, None, False]


def test_collector_should_close_coverage_when_player_disappears_or_connection_stops() -> None:
    collector = MatchCollector()
    snapshot = update(collector, flags={"bOnGround": False})
    collector.interrupt(LATER)
    collector.interrupt(LATER)

    assert len(snapshot.events) == 2
    assert list(snapshot.events.values())[-1].details == {
        "previous": False,
        "value": None,
    }
    assert not snapshot.states.values


def test_collector_should_end_only_departed_player_states_and_discard_stale_shortcuts() -> None:
    collector = MatchCollector()
    snapshot = update(collector, flags={"bOnGround": False})

    emit(collector, "PlayerLeft", {"PrimaryId": PLAYER["PrimaryId"], "PlayerName": "One"}, LATER)

    assert PLAYER["PrimaryId"] not in snapshot.states.values
    assert PLAYER["PrimaryId"] not in snapshot.shortcuts.values()
    assert OTHER["PrimaryId"] in snapshot.shortcuts.values()
    transitions = [event for event in snapshot.events.values() if event.origin == "state"]
    assert [event.details["value"] for event in transitions] == [False, None]


def test_collector_should_not_measure_pause_or_post_match_ticks_as_playtime() -> None:
    collector = MatchCollector()
    snapshot = update(collector, flags={"bOnGround": True})
    emit(collector, "MatchPaused")
    update(collector, flags={"bOnGround": False})
    assert len([event for event in snapshot.events.values() if event.origin == "state"]) == 2
    emit(collector, "MatchUnpaused")
    update(collector, flags={"bOnGround": False})
    emit(collector, "MatchEnded", {"WinnerTeamNum": 0})
    update(collector, flags={"bOnGround": True})

    states = [event for event in snapshot.events.values() if event.origin == "state"]
    assert [event.details["value"] for event in states] == [True, None, False, None]


def test_collector_should_preserve_future_event_position_without_raw_payload(
    store: MatchStore,
) -> None:
    snapshot = emit(
        MatchCollector(),
        "FutureEvent",
        {
            "Location": {"X": 0, "Y": -10, "Z": 20},
            "Telemetry": [1, 2, 3],
        },
    )
    store.save_details(snapshot)
    row = store.events("match")[0]

    assert (row["x"], row["y"], row["z"]) == (0, -10, 20)
    assert row["position_subject"] is None
    assert json.loads(row["details_json"]) == {}


def test_collector_should_use_event_clock_and_ignore_nonfinite_positions(store: MatchStore) -> None:
    collector = MatchCollector()
    update(collector)
    snapshot = emit(
        collector,
        "BallHit",
        {
            "TimeSeconds": 7,
            "bOvertime": True,
            "Ball": {
                "Location": {"X": float("nan"), "Y": float("inf"), "Z": 0},
                "PreHitSpeed": True,
                "PostHitSpeed": float("inf"),
            },
        },
    )
    store.save_details(snapshot)
    row = store.events("match")[0]

    assert row["time_seconds"] == 7 and row["overtime"] == 1
    assert (row["x"], row["y"], row["z"]) == (None, None, 0)
    assert row["speed"] is None
    assert json.loads(row["details_json"]) == {}


def test_storage_should_preserve_late_events_without_overwriting_final_summary(
    store: MatchStore,
) -> None:
    final = update(MatchCollector())
    final.final_observed = True
    final.blue_score = 5
    store.save_details(final)
    partial = emit(MatchCollector(), "PlayerLeft", PLAYER)
    partial.blue_score = 0

    store.save_details(partial)

    assert store.detail("match")["blue_score"] == 5
    assert store.events("match")[0]["kind"] == "PlayerLeft"


def test_migration_should_preserve_existing_event_ids_coordinates_and_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.sqlite3"
    store = MatchStore(path)
    snapshot = emit(
        MatchCollector(),
        "GoalScored",
        {
            "GoalSpeed": 900,
            "ImpactLocation": {"X": -20, "Y": 5000, "Z": 100},
        },
    )
    store.save_details(snapshot)
    event_id = store.events("match")[0]["id"]
    with store.connection:
        store.connection.execute("DROP TABLE match_event_players")
        for column in ("source_event", "origin", "position_subject", "details_json"):
            store.connection.execute(f"ALTER TABLE match_events DROP COLUMN {column}")
        store.connection.execute("PRAGMA user_version = 5")
    store.close()

    for _ in range(2):
        reopened = MatchStore(path)
        try:
            row = reopened.events("match")[0]
            assert row["id"] == event_id
            assert (row["x"], row["y"], row["z"]) == (-20, 5000, 100)
            assert row["source_event"] == "GoalScored"
            assert row["position_subject"] == "ball"
            assert reopened.connection.execute("PRAGMA user_version").fetchone()[0] == 6
            assert reopened.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            reopened.close()


def test_collector_should_preserve_pending_old_events_until_storage_succeeds(
    store: MatchStore,
) -> None:
    collector = MatchCollector()
    for guid in ("first", "second", "third"):
        collector.observe({"Event": "BallHit", "Data": {"MatchGuid": guid}}, TIME)

    assert len(collector.snapshots) == 3
    for snapshot in collector.snapshots.values():
        store.save_details(snapshot)
        snapshot.events.clear()
    collector.prune()

    assert tuple(collector.snapshots) == ("second", "third")
    assert len(store.events("first")) == 1


def test_storage_should_roll_back_event_and_participants_as_one_transaction(
    store: MatchStore,
) -> None:
    collector = MatchCollector()
    update(collector)
    snapshot = emit(collector, "BallHit", {"Players": [PLAYER]})

    def deny_participant(
        action: int,
        first: str | None,
        second: str | None,
        database: str | None,
        trigger: str | None,
    ) -> int:
        if action == sqlite3.SQLITE_INSERT and first == "match_event_players":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    store.connection.set_authorizer(deny_participant)
    try:
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            store.save_details(snapshot)
    finally:
        store.connection.set_authorizer(None)

    assert store.detail("match") is None
    assert store.events("match") == []
    assert len(snapshot.events) == 1
    store.save_details(snapshot)
    row = store.events("match")[0]
    assert len(store.event_participants(row["id"])) == 1


def test_migration_should_roll_back_all_new_columns_when_version_write_fails(
    store: MatchStore,
) -> None:
    with store.connection:
        store.connection.execute("DROP TABLE match_event_players")
        for column in ("source_event", "origin", "position_subject", "details_json"):
            store.connection.execute(f"ALTER TABLE match_events DROP COLUMN {column}")
        store.connection.execute("PRAGMA user_version = 5")

    def deny_version(
        action: int,
        first: str | None,
        second: str | None,
        database: str | None,
        trigger: str | None,
    ) -> int:
        if action == sqlite3.SQLITE_PRAGMA and first == "user_version" and second == "6":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    store.connection.set_authorizer(deny_version)
    try:
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            migrate_events(store.connection)
    finally:
        store.connection.set_authorizer(None)

    assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 5
    columns = {row[1] for row in store.connection.execute("PRAGMA table_info(match_events)")}
    assert "details_json" not in columns
    migrate_events(store.connection)
    assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 6
