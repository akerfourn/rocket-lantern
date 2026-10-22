"""Opponent-only goal frame counts, attribution, lifecycle and native live display."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rocket_lantern.live_match import LiveMatchState
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.live_team_table import LiveTeamTable
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow

TIME = "2026-10-22T19:00:00+00:00"
POST_COLUMN = 5


def state_message(guid: str = "match") -> dict[str, object]:
    return {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": guid,
            "Game": {"TimeSeconds": 120},
            "Players": [
                {"PrimaryId": "blue", "Name": "Same", "TeamNum": 0, "Shortcut": 1},
                {"PrimaryId": "orange", "Name": "Same", "TeamNum": 1, "Shortcut": 1},
            ],
        },
    }


def post_hit(team: int = 0, impact_y: float = 5120) -> dict[str, object]:
    return {
        "Event": "CrossbarHit",
        "Data": {
            "MatchGuid": "match",
            "BallLocation": {"X": 890, "Y": impact_y, "Z": 300},
            "BallLastTouch": {"Player": {"Name": "Same", "TeamNum": team, "Shortcut": 1}},
        },
    }


@pytest.mark.parametrize(
    ("team", "impact_y", "expected"),
    [
        (0, 5120, {"blue": 1}),
        (0, -5120, {}),
        (1, -5120, {"orange": 1}),
        (1, 5120, {}),
    ],
)
def test_post_count_should_include_only_the_last_touchers_opponent_goal(
    team: int, impact_y: float, expected: dict[str, int]
) -> None:
    state = LiveMatchState()
    state.observe(state_message(), TIME, False)
    event = post_hit(team, impact_y)

    state.observe(event, TIME, False)
    state.observe(state_message(), TIME, False)

    assert state.opponent_post_hits == expected
    assert state.snapshot.events == {}, "Keep a counter, not live event history"
    assert event["Data"]["BallLocation"]["Y"] == impact_y


@pytest.mark.parametrize(
    "overrides",
    [
        {"BallLocation": None},
        {"BallLocation": {"Y": 0}},
        {"BallLocation": {"Y": float("nan")}},
        {"BallLastTouch": None},
        {"BallLastTouch": {"Player": {"PrimaryId": "blue"}}},
        {"BallLastTouch": {"Player": {"PrimaryId": "absent", "TeamNum": 0}}},
        {"BallLastTouch": {"Player": {"Name": "Same", "TeamNum": 0, "Shortcut": 99}}},
        {"MatchGuid": "another-match"},
        {"bReplay": True},
    ],
)
def test_post_count_should_not_guess_missing_or_invalid_attribution(
    overrides: dict[str, object],
) -> None:
    state = LiveMatchState()
    state.observe(state_message(), TIME, False)
    event = post_hit()
    event["Data"].update(overrides)

    state.observe(event, TIME, False)

    assert state.opponent_post_hits == {}


def test_post_count_should_use_the_events_team_if_the_cached_assignment_is_older() -> None:
    state = LiveMatchState()
    state.observe(state_message(), TIME, False)
    event = post_hit(1, -5120)
    event["Data"]["BallLastTouch"]["Player"]["PrimaryId"] = "blue"

    state.observe(event, TIME, False)

    assert state.opponent_post_hits == {"blue": 1}


def test_post_count_should_ignore_goal_replays_and_reset_after_history_or_new_matches() -> None:
    state = LiveMatchState()
    state.observe(state_message(), TIME, False)
    state.observe(post_hit(), TIME, False)
    state.observe({"Event": "GoalReplayStart", "Data": {"MatchGuid": "match"}}, TIME, False)
    state.observe(post_hit(), TIME, False)
    assert state.opponent_post_hits == {"blue": 1}

    state.observe({"Event": "GoalReplayEnd", "Data": {"MatchGuid": "match"}}, TIME, False)
    state.observe(post_hit(), TIME, False)
    assert state.opponent_post_hits == {"blue": 2}

    state.observe({"Event": "ReplayCreated", "Data": {}}, TIME, True)
    assert state.opponent_post_hits == {}
    state.observe(state_message(), TIME, False)
    state.observe(post_hit(), TIME, False)
    state.observe(state_message("next"), TIME, False)
    assert state.opponent_post_hits == {}


def test_post_count_should_support_offline_matches_and_clear_on_departure_or_disconnect() -> None:
    state = LiveMatchState()
    update = state_message("")
    event = post_hit()
    del event["Data"]["MatchGuid"]
    state.observe(update, TIME, False)
    state.observe(event, TIME, False)
    assert state.opponent_post_hits == {"blue": 1}

    state.observe({"Event": "MatchDestroyed", "Data": {}}, TIME, False)
    assert state.opponent_post_hits == {}
    state.observe(update, TIME, False)
    state.observe(event, TIME, False)
    state.clear("Disconnected")
    assert state.opponent_post_hits == {}


def player_post_counts(table: LiveTeamTable) -> dict[str, str]:
    counts = {}
    for row in range(table.rowCount()):
        primary_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if primary_id is not None:
            counts[primary_id] = table.item(row, POST_COLUMN).text()
    return counts


def test_live_panel_should_refresh_post_counts_and_team_totals_independently_of_selection(
    application: QApplication,
) -> None:
    panel = LiveMatchPanel("blue")
    panel.observe(state_message(), TIME, False)
    assert player_post_counts(panel.players) == {"blue": "0", "orange": "0"}

    panel.observe(post_hit(), TIME, False)
    panel.observe(post_hit(), TIME, False)
    panel.observe(post_hit(1, -5120), TIME, False)
    assert player_post_counts(panel.players) == {"blue": "2", "orange": "1"}
    assert panel.players.item(0, POST_COLUMN).text() == "2"
    assert panel.players.item(3, POST_COLUMN).text() == "1"

    panel.set_player("orange")
    assert player_post_counts(panel.players) == {"orange": "1", "blue": "2"}
    assert panel.players.item(0, POST_COLUMN).text() == "1"
    panel.observe(post_hit(0, -5120), TIME, False)
    assert player_post_counts(panel.players)["blue"] == "2", "An own post never counts"
    panel.close()


def test_live_post_filter_should_leave_all_original_events_in_storage(
    application: QApplication,
) -> None:
    store = MatchStore(":memory:")
    store.set_setting("evaluation_hotkeys_enabled", "0")
    window = MainWindow(store)
    try:
        window.client.message_received.emit(json.dumps(state_message()))
        window.client.message_received.emit(json.dumps(post_hit(0, -5120)))
        window.client.message_received.emit(json.dumps(post_hit()))

        assert window.live.state.opponent_post_hits == {"blue": 1}
        events = store.events("match")
        assert [event["kind"] for event in events] == ["CrossbarHit", "CrossbarHit"]
        assert [event["y"] for event in events] == [-5120, 5120]
    finally:
        window.close()
        store.close()
