"""Offscreen GUI tests using synthetic messages and an in-memory database."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_installations import DiscoveryReport, GameInstallation
from rocket_lantern.game_installations_panel import ConfigurationCheck
from rocket_lantern.match_data import MatchCollector
from rocket_lantern.match_detail_dialog import MatchDetailDialog
from rocket_lantern.packet_configuration import RateConfiguration
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    widget.show()
    application.processEvents()
    yield widget
    widget.close()
    store.close()


def test_settings_should_start_compact_without_configuration_results(
    window: MainWindow, application: QApplication
) -> None:
    window.settings_button.click()
    application.processEvents()

    assert window.settings.height() < 600
    assert not window.settings.game_installations.results.isVisible()


@pytest.mark.parametrize("count", [1, 2, 8])
def test_settings_should_grow_for_results_and_shrink_when_none_remain(
    window: MainWindow, application: QApplication, tmp_path: Path, count: int
) -> None:
    window.settings_button.click()
    application.processEvents()
    compact_height = window.settings.height()
    panel = window.settings.game_installations
    installations = tuple(
        GameInstallation("Steam", tmp_path / str(index), None) for index in range(count)
    )
    configurations = tuple(RateConfiguration(item, rate=10) for item in installations)

    panel._completed(ConfigurationCheck(DiscoveryReport(installations), configurations))
    application.processEvents()

    assert window.settings.height() > compact_height
    assert panel.results.isVisible()
    assert panel.results.height() <= 270
    window.settings.close()
    window.settings_button.click()
    application.processEvents()
    assert window.settings.height() > compact_height
    assert panel.results.isVisible()

    panel._completed(ConfigurationCheck(DiscoveryReport(), ()))
    application.processEvents()
    assert window.settings.height() <= compact_height
    assert not panel.results.isVisible()


def test_settings_should_limit_results_height_to_available_screen(
    window: MainWindow,
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    screen = Mock()
    screen.availableGeometry.return_value = QRect(0, 0, 1000, 600)
    monkeypatch.setattr(window.settings, "screen", lambda: screen)
    window.settings_button.click()
    application.processEvents()
    installations = tuple(
        GameInstallation("Steam", tmp_path / str(index), None) for index in range(8)
    )
    configurations = tuple(RateConfiguration(item, rate=10) for item in installations)

    window.settings.game_installations._completed(
        ConfigurationCheck(DiscoveryReport(installations), configurations)
    )
    application.processEvents()

    assert window.settings.frameGeometry().height() <= 600
    assert window.settings.frameGeometry().bottom() <= 599
    assert window.settings.game_installations.results.height() < 270


def test_settings_should_return_to_previous_view_without_reconnecting(window: MainWindow) -> None:
    window.client.start = Mock()
    window.tabs.setCurrentIndex(1)
    window.settings_button.click()
    assert window.settings.isVisible()
    assert window.settings.isWindow()
    assert not window.settings_button.icon().isNull()
    window.settings.close_button.click()
    assert not window.settings.isVisible()
    assert window.matches.counters.isVisible()
    assert window.tabs.currentIndex() == 1
    window.client.start.assert_not_called()


def test_settings_should_persist_startup_tab_without_switching_current_view(
    window: MainWindow,
) -> None:
    window.settings.default_tab.setCurrentIndex(1)
    assert window.store.setting("default_tab") == "live"
    assert window.tabs.currentIndex() == 0
    reopened = MainWindow(window.store)
    try:
        assert reopened.tabs.currentIndex() == 1
        assert reopened.settings.default_tab.currentData() == "live"
    finally:
        reopened.close()


def test_settings_should_save_port_and_reconnect_only_on_request(window: MainWindow) -> None:
    window.client.start = Mock()
    window.port.setValue(49125)
    assert window.store.setting("port") == "49125"
    window.client.start.assert_not_called()
    window.settings.reconnect.click()
    window.client.start.assert_called_once_with(49125)


def test_settings_should_save_desired_packet_rate_without_applying_game_configuration(
    window: MainWindow,
) -> None:
    panel = window.settings.game_installations
    panel.detector = Mock()
    panel.packet_rate.setValue(20)

    assert window.store.setting("packet_send_rate") == "20"
    panel.detector.assert_not_called()
    reopened = MainWindow(window.store)
    try:
        assert reopened.settings.game_installations.packet_rate.value() == 20
    finally:
        reopened.close()


@pytest.mark.parametrize("saved", ["", "invalid", "matches"])
def test_settings_should_default_to_matches_when_preference_is_missing_or_invalid(
    application: QApplication, saved: str
) -> None:
    store = MatchStore(":memory:")
    store.set_setting("default_tab", saved)
    widget = MainWindow(store)
    try:
        assert widget.tabs.currentIndex() == 0
        assert widget.settings.default_tab.currentData() == "matches"
    finally:
        widget.close()
        store.close()


def send_state(window: MainWindow, encode_data: bool = False) -> None:
    """Deliver an event through the same signal used by the Qt socket."""
    data = {
        "MatchGuid": "gui-match",
        "Players": [{"PrimaryId": "Epic|test|0", "Name": "Test", "TeamNum": 0}],
        "Game": {"PlaylistId": 11},
    }
    wire_data: object = data
    if encode_data:
        wire_data = json.dumps(data)
    window.client.message_received.emit(json.dumps({"Event": "UpdateState", "Data": wire_data}))


@pytest.mark.parametrize("encode_data", [False, True])
def test_window_should_show_saved_win_when_selected_player_wins(
    window: MainWindow,
    encode_data: bool,
) -> None:
    send_state(window, encode_data)
    window.matches.player.setCurrentIndex(1)
    send_state(window, encode_data)

    result: object = {"MatchGuid": "gui-match", "WinnerTeamNum": 0}
    if encode_data:
        result = json.dumps(result)
    window.client.message_received.emit(json.dumps({"Event": "MatchEnded", "Data": result}))

    assert window.matches.history.rowCount() == 1
    assert window.matches.history.item(0, 1).text() == "Victoire"
    assert "100,0 %" in window.matches.counters.text()
    assert "2v2 classé" in window.matches.history.item(0, 2).text()
    assert window.store.setting("player_id") == "Epic|test|0"
    assert "[Rejet]" not in window.logs.text.toPlainText()
    assert "gui-match" not in window.logs.text.toPlainText()
    assert "Epic|test|0" not in window.logs.text.toPlainText()


def test_window_should_mark_unknown_when_connection_lost_signal_arrives(window: MainWindow) -> None:
    send_state(window)
    window.matches.player.setCurrentIndex(1)
    send_state(window)

    window.client.connection_lost.emit()

    assert window.matches.history.item(0, 1).text() == "Inconnu"
    assert window.store.summary("Epic|test|0").losses == 0


def test_window_should_report_bad_message_when_json_is_invalid(window: MainWindow) -> None:
    window.client.message_received.emit("not JSON")

    assert "invalide" in window.notice.text()
    assert window.matches.history.rowCount() == 0
    assert "JSON invalide" in window.logs.text.toPlainText()
    assert window.logs.received_count == 1


def test_window_should_log_every_event_when_no_player_is_selected(window: MainWindow) -> None:
    send_state(window)
    send_state(window)
    window.client.message_received.emit(
        json.dumps({"Event": "GoalScored", "Data": {"MatchGuid": "gui-match"}})
    )

    text = window.logs.text.toPlainText()
    assert text.count('"Event":"UpdateState"') == 2
    assert '"Event":"GoalScored"' in text
    assert window.logs.received_count == 3
    assert "sélectionne ton joueur" in text
    assert "Epic|test|0" not in text
    assert '"Name":"Test"' not in text


def test_window_should_show_live_playlist_when_player_has_not_been_selected(
    window: MainWindow,
) -> None:
    send_state(window)

    assert "2v2 classé" in window.matches.session.text()
    assert window.matches.history.rowCount() == 0


def test_window_should_show_private_match_when_event_has_no_guid(window: MainWindow) -> None:
    window.client.message_received.emit(
        json.dumps({"Event": "UpdateState", "Data": {"Game": {"PlaylistId": 6}, "Players": []}})
    )

    assert "Match privé" in window.matches.session.text()
    assert "sans MatchGuid" in window.matches.observation.text()
    assert "UpdateState" in window.logs.text.toPlainText()


def test_window_should_log_rejection_when_valid_json_has_invalid_schema(window: MainWindow) -> None:
    window.client.message_received.emit('{"Event":"UpdateState","Data":null}')

    text = window.logs.text.toPlainText()
    assert '"Event":"UpdateState"' in text
    assert "[Rejet]" in text
    assert "Event et Data" in text


def test_window_should_switch_counts_when_latest_playlist_changes(window: MainWindow) -> None:
    window.store.save(MatchResult("trios", "test", "2026-01-01T18:00:00+00:00", 13, "win"))
    window.matches.refresh(window.store, "test")
    assert window.matches.history.rowCount() == 0
    window.matches.period.setCurrentIndex(1)
    assert "1 victoires" in window.matches.counters.text()

    window.matches.observe({"Event": "UpdateState", "Data": {"Game": {"PlaylistId": 11}}}, "")
    assert "0 victoires" in window.matches.counters.text()
    assert window.matches.history.rowCount() == 0
    window.matches.playlist_filter.setCurrentIndex(1)
    assert "1 victoires" in window.matches.counters.text()
    window.matches.playlist_filter.setCurrentIndex(0)
    window.matches.observe({"Event": "UpdateState", "Data": {"Game": {"PlaylistId": 13}}}, "")
    assert "1 victoires" in window.matches.counters.text()


def test_window_should_reset_current_counts_when_new_session_button_is_clicked(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2026, 10, 4, 12, 5, tzinfo=UTC)
    monkeypatch.setattr("rocket_lantern.window.datetime", clock)
    monkeypatch.setattr("rocket_lantern.match_panel.datetime", clock)
    assert not window.matches.new_session.isEnabled()
    send_state(window)
    window.matches.player.setCurrentIndex(1)
    window.store.save(MatchResult("old", "Epic|test|0", "2026-10-04T12:00:00+00:00", 11, "win"))
    window.matches.refresh(window.store, "Epic|test|0")
    old_id = window.store.sessions("Epic|test|0")[0]["id"]
    assert "1 victoires" in window.matches.counters.text()

    window.matches.new_session.click()

    assert window.matches.period.currentData() == "current"
    assert "0 victoires" in window.matches.counters.text()
    assert window.matches.history.rowCount() == 0
    assert window.store.summary("Epic|test|0").wins == 1
    assert len(window.store.sessions("Epic|test|0")) == 2
    send_state(window)
    window.client.message_received.emit(
        json.dumps({"Event": "MatchEnded", "Data": {"MatchGuid": "gui-match", "WinnerTeamNum": 0}})
    )
    assert "1 victoires" in window.matches.counters.text()
    assert window.store.summary("Epic|test|0").wins == 2
    window.matches.period.setCurrentIndex(window.matches.period.findData(old_id))
    assert window.matches.history.rowCount() == 1
    assert window.matches.history.item(0, 0).data(Qt.ItemDataRole.UserRole) == "old"


def test_window_should_enrich_match_details_when_final_stats_arrive_after_result(
    window: MainWindow,
) -> None:
    send_state(window)
    window.matches.player.setCurrentIndex(1)
    send_state(window)
    window.client.message_received.emit(
        json.dumps(
            {
                "Event": "GoalScored",
                "Data": {
                    "MatchGuid": "gui-match",
                    "Scorer": {"PrimaryId": "Epic|test|0", "TeamNum": 0},
                    "GoalSpeed": 1500,
                    "GoalTime": 20,
                },
            }
        )
    )
    window.client.message_received.emit(
        json.dumps(
            {
                "Event": "MatchEnded",
                "Data": {
                    "MatchGuid": "gui-match",
                    "WinnerTeamNum": 0,
                },
            }
        )
    )
    window.client.message_received.emit(
        json.dumps(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": "gui-match",
                    "Players": [
                        {
                            "PrimaryId": "Epic|test|0",
                            "Name": "Test",
                            "TeamNum": 0,
                            "Goals": 2,
                            "Saves": 0,
                        }
                    ],
                    "Game": {
                        "PlaylistId": 11,
                        "bHasWinner": True,
                        "Winner": "Blue",
                        "Teams": [
                            {"Name": "Blue", "TeamNum": 0, "Score": 2},
                            {"Name": "Orange", "TeamNum": 1, "Score": 1},
                        ],
                    },
                },
            }
        )
    )

    assert window.store.summary("Epic|test|0").wins == 1
    assert window.store.participants("gui-match")[0]["goals"] == 2
    assert window.store.detail("gui-match")["final_observed"] == 1
    assert window.matches.statistics.values["goals"].text() == "2"
    assert window.matches.statistics.values["saves"].text() == "0"
    assert window.matches.statistics.averages["goals"].text() == "2,0 / match · 1/1"
    dialog = MatchDetailDialog(window.store, "gui-match", window)
    assert dialog.players.rowCount() == 1
    assert dialog.events.rowCount() == 1
    assert dialog.players.item(0, 3).text() == "2"
    assert dialog.players.item(0, 6).text() == "0"
    dialog.close()


@pytest.mark.parametrize("team, expected", [(0, "<b><u>2</u></b> – 1"), (1, "2 – <b><u>1</u></b>")])
def test_score_should_emphasize_selected_team_when_viewing_saved_match(
    window: MainWindow,
    team: int,
    expected: str,
) -> None:
    collector = MatchCollector()
    snapshot = collector.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "score-match",
                "Players": [{"PrimaryId": "test", "Name": "Test", "TeamNum": team}],
                "Game": {
                    "bHasWinner": True,
                    "Teams": [
                        {"TeamNum": 0, "Score": 2},
                        {"TeamNum": 1, "Score": 1},
                    ],
                },
            },
        },
        "2026-01-01T18:00:00+00:00",
    )
    assert snapshot is not None
    window.store.save_details(snapshot)
    window.store.save(MatchResult("score-match", "test", snapshot.observed_at, 11, "win"))
    window.matches.period.setCurrentIndex(1)
    window.matches.refresh(window.store, "test")

    assert expected in window.matches.history.cellWidget(0, 3).text()
    dialog = MatchDetailDialog(window.store, "score-match", window, "test")
    assert expected in dialog.score.text()
    dialog.close()


def test_window_should_keep_filters_and_session_actions_on_the_same_row(
    window: MainWindow,
    application: QApplication,
) -> None:
    application.processEvents()
    controls = window.matches.controls.layout()
    widgets = (
        window.matches.player,
        window.matches.period,
        window.matches.playlist_filter,
        window.matches.new_session,
        window.matches.session_details,
    )

    assert [controls.itemAt(index).widget() for index in (1, 3, 5, 6, 7)] == list(widgets)
    centers = [widget.geometry().center().y() for widget in widgets]
    assert max(centers) - min(centers) <= 1
