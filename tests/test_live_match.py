"""Synthetic live observations: missing data, lifecycle, selection and no telemetry writes."""

import json
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern.live_match import LiveMatchState
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult
from rocket_lantern.window import MainWindow

OBSERVED_AT = "2026-10-08T19:00:00+00:00"


def state_message(guid: str = "live-match") -> dict[str, object]:
    """An ordinary update with a teammate's boost, not spectator-specific gating."""
    return {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": guid,
            "Game": {
                "PlaylistId": 11,
                "Arena": "Stadium_P",
                "TimeSeconds": 123,
                "bOvertime": False,
                "bReplay": False,
                "Teams": [{"TeamNum": 0, "Score": 2}, {"TeamNum": 1, "Score": 1}],
                "Ball": {"Speed": 850.5, "TeamNum": 1},
            },
            "Players": [
                {"PrimaryId": "local", "Name": "Test", "TeamNum": 0, "Boost": 0, "Goals": 0},
                {"PrimaryId": "teammate", "Name": "Test", "TeamNum": 0, "Boost": 45},
                {"PrimaryId": "opponent", "Name": "Other", "TeamNum": 1, "Saves": 0},
            ],
        },
    }


def event_message(event: str, guid: str = "live-match", **values: object) -> dict[str, object]:
    return {"Event": event, "Data": {"MatchGuid": guid, **values}}


def test_live_state_should_keep_only_latest_values_and_distinguish_zero_from_missing() -> None:
    state = LiveMatchState()
    state.observe(state_message(), OBSERVED_AT, False)

    assert state.snapshot is not None
    assert state.snapshot.blue_score == 2
    assert state.snapshot.time_seconds == 123
    assert state.ball_speed == 850.5
    assert state.last_touch_team == 1
    assert state.boost == {"local": 0, "teammate": 45, "opponent": None}
    assert state.snapshot.players["local"].goals == 0
    assert state.snapshot.players["teammate"].goals is None

    state.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "live-match",
                "Game": {},
                "Players": [{"PrimaryId": "local", "Name": "Test", "TeamNum": 0}],
            },
        },
        OBSERVED_AT,
        False,
    )

    assert state.boost == {"local": None}, "An omitted boost must not retain an older value"
    assert state.ball_speed is None
    assert state.snapshot.blue_score is None
    assert set(state.snapshot.players) == {"local"}, "Departed players are not live participants"


@pytest.mark.parametrize("boost", [True, -1, 101, "45", None])
def test_live_state_should_reject_invalid_boost_values(boost: object) -> None:
    message = {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": "live-match",
            "Game": {},
            "Players": [{"PrimaryId": "local", "Name": "Test", "TeamNum": 0, "Boost": boost}],
        },
    }
    state = LiveMatchState()
    state.observe(message, OBSERVED_AT, False)

    assert state.boost["local"] is None


def test_live_state_should_ignore_other_matches_and_use_received_overtime_clock() -> None:
    state = LiveMatchState()
    state.observe(state_message(), OBSERVED_AT, False)
    state.observe(event_message("ClockUpdatedSeconds", "other", TimeSeconds=9), OBSERVED_AT, False)
    assert state.snapshot.time_seconds == 123

    state.observe(
        event_message("ClockUpdatedSeconds", TimeSeconds=7, bOvertime=True), OBSERVED_AT, False
    )
    assert state.snapshot.time_seconds == 7
    assert state.snapshot.overtime is True
    state.observe(event_message("MatchPaused"), OBSERVED_AT, False)
    assert state.phase == "En pause"
    state.observe(event_message("MatchUnpaused"), OBSERVED_AT, False)
    assert state.phase == "En cours"


def test_live_state_should_preserve_live_values_during_goal_replay_and_exclude_history() -> None:
    state = LiveMatchState()
    state.observe(state_message(), OBSERVED_AT, False)
    state.observe(event_message("GoalReplayStart"), OBSERVED_AT, False)
    state.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "live-match",
                "Game": {"bReplay": True, "TimeSeconds": 999},
            },
        },
        OBSERVED_AT,
        False,
    )
    state.observe(event_message("ClockUpdatedSeconds", TimeSeconds=999), OBSERVED_AT, False)

    assert state.snapshot.time_seconds == 123
    assert state.boost["teammate"] == 45
    assert state.goal_replay

    state.observe(event_message("GoalReplayEnd"), OBSERVED_AT, False)
    assert not state.goal_replay
    state.observe(event_message("ReplayCreated"), OBSERVED_AT, True)
    state.observe(state_message(), OBSERVED_AT, True)
    assert state.snapshot is None
    assert state.boost == {}
    assert "Replay historique" in state.phase


def test_live_state_should_clear_values_on_departure_and_match_transition() -> None:
    state = LiveMatchState()
    state.observe(state_message(), OBSERVED_AT, False)
    state.observe(event_message("MatchDestroyed", "other"), OBSERVED_AT, False)
    assert state.snapshot is not None
    state.observe(event_message("MatchDestroyed"), OBSERVED_AT, False)
    assert state.snapshot is None
    assert state.boost == {}
    state.observe(state_message(), OBSERVED_AT, False)
    state.observe(event_message("MatchCreated", "next"), OBSERVED_AT, False)
    assert state.snapshot is None
    state.observe(state_message("next"), OBSERVED_AT, False)
    assert state.snapshot.guid == "next"


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    widget.show()
    application.processEvents()
    yield widget
    widget.close()
    store.close()


def test_window_should_show_filtered_summary_and_controls_above_every_tab(
    window: MainWindow,
) -> None:
    assert window.matches.controls.parentWidget() is window.centralWidget()
    assert window.matches.counters.parentWidget() is window.centralWidget()
    assert window.matches.counters.geometry().bottom() < window.tabs.geometry().top()
    assert window.tabs.tabText(window.tabs.indexOf(window.live)) == "Partie en cours"
    window.tabs.setCurrentWidget(window.live)
    assert window.matches.counters.isVisible()
    assert window.matches.player.isVisible()
    window.tabs.setCurrentWidget(window.logs)
    assert window.matches.counters.isVisible()


def test_window_should_keep_filters_and_actions_aligned_when_labels_are_long(
    window: MainWindow, application: QApplication
) -> None:
    minimum_filter_width = window.matches.controls.minimumSizeHint().width()
    window.matches.player.addItem("Un pseudonyme particulièrement long", "long-player")
    window.matches.period.addItem("Session #123 du 08/10/2026 19:00", 123)
    window.resize(850, 800)
    application.processEvents()

    widgets = (
        window.matches.player,
        window.matches.period,
        window.matches.playlist_filter,
        window.matches.new_session,
        window.matches.session_details,
    )
    centers = [widget.geometry().center().y() for widget in widgets]
    assert max(centers) - min(centers) <= 1
    assert window.matches.controls.minimumSizeHint().width() == minimum_filter_width, (
        "Long labels must not expand the minimum filter width"
    )


def test_window_should_display_teammate_boost_and_select_by_id_not_duplicate_name(
    window: MainWindow,
) -> None:
    window.client.message_received.emit(json.dumps(state_message()))
    assert window.live.clock.text() == "2:03"
    assert window.live.players.rowCount() == 3
    window.matches.player.setCurrentIndex(window.matches.player.findData("teammate"))

    assert window.live.boost.isEnabled()
    assert window.live.boost.value() == 45
    assert "<u>2</u>" in window.live.score.text()
    assert not window.live.players.item(0, 0).font().bold()
    assert window.live.players.item(1, 0).font().bold()
    window.matches.player.setCurrentIndex(window.matches.player.findData("local"))
    assert window.live.boost.isEnabled()
    assert window.live.boost.value() == 0
    window.matches.player.setCurrentIndex(window.matches.player.findData("opponent"))
    assert not window.live.boost.isEnabled()
    assert "champ non reçu" in window.live.boost.format()
    assert "<u>1</u>" in window.live.score.text()


def test_window_should_clear_stale_live_values_without_writing_periodic_telemetry(
    window: MainWindow,
) -> None:
    window.client.message_received.emit(json.dumps(state_message()))
    window.client.message_received.emit(json.dumps(state_message()))
    assert window.store.history("") == []
    assert window.store.connection.execute("SELECT COUNT(*) FROM match_details").fetchone()[0] == 0
    window.client.connection_lost.emit()

    assert window.live.state.snapshot is None
    assert window.live.players.rowCount() == 0
    assert window.live.clock.text() == "—:—"
    assert not window.live.boost.isEnabled()


def test_window_should_update_global_counts_from_filters_while_live_tab_is_open(
    window: MainWindow,
) -> None:
    window.client.message_received.emit(json.dumps(state_message()))
    window.matches.player.setCurrentIndex(window.matches.player.findData("local"))
    window.store.save(MatchResult("old-duos", "local", OBSERVED_AT, 11, "win"))
    window.store.save(MatchResult("old-trios", "local", OBSERVED_AT, 13, "loss"))
    window.matches.refresh(window.store, "local")
    window.matches.period.setCurrentIndex(window.matches.period.findData("all"))
    window.tabs.setCurrentWidget(window.live)

    assert window.matches.counters.wins.text() == "1 victoires"
    assert window.matches.counters.losses.text() == "0 défaites"
    window.matches.playlist_filter.setCurrentIndex(window.matches.playlist_filter.findData(13))
    assert window.matches.counters.wins.text() == "0 victoires"
    assert window.matches.counters.losses.text() == "1 défaites"
    assert "3v3 classé" in window.matches.counters.context.text()
    assert "2v2 classé" in window.live.context.text(), "History filters must not filter live data"
    assert window.live.boost.value() == 0


def test_window_should_not_write_live_ticks_even_with_a_tracked_player(window: MainWindow) -> None:
    window.client.message_received.emit(json.dumps(state_message()))
    window.matches.player.setCurrentIndex(window.matches.player.findData("teammate"))
    window.client.message_received.emit(json.dumps(state_message()))
    previous_changes = window.store.connection.total_changes

    window.client.message_received.emit(json.dumps(state_message()))
    window.client.message_received.emit(
        json.dumps(event_message("ClockUpdatedSeconds", TimeSeconds=122))
    )

    assert window.store.connection.total_changes == previous_changes
    assert window.live.boost.value() == 45
    assert window.live.clock.text() == "2:02"


def test_live_state_should_not_show_boost_for_a_missing_car_or_infer_it_from_pickups() -> None:
    state = LiveMatchState()
    state.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "live-match",
                "Game": {},
                "Players": [
                    {
                        "PrimaryId": "local",
                        "Name": "Test",
                        "TeamNum": 0,
                        "Boost": 100,
                        "bHasCar": False,
                    }
                ],
            },
        },
        OBSERVED_AT,
        False,
    )
    state.observe(event_message("BoostPickup", BoostAmount=100), OBSERVED_AT, False)

    assert state.boost["local"] is None
