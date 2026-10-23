"""Detection controls tracking; a history filter cannot change the boost team."""

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from rocket_lantern.game_presence import GamePresenceApi, GamePresenceMonitor
from rocket_lantern.live_team_table import ENCOUNTER_ROLE
from rocket_lantern.local_player import LocalPlayer, LocalPlayerLog
from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.player_encounters import EncounterScope
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult
from rocket_lantern.window import MainWindow


def write_login(path: Path, account: str = "Steam|123|0", status: str = "LS_LoggedIn") -> None:
    path.write_text(
        "[0001.23] Party: HandleLocalPlayerLoginStatusChanged "
        f"PlayerName=Test PlayerID={account} LoginStatus={status} IsPrimary=True\n",
        encoding="utf-8",
    )


@pytest.fixture
def window(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MainWindow]:
    api = Mock(spec=GamePresenceApi)
    api.game_process_ids.return_value = frozenset({100})
    api.foreground_window.return_value = 10
    api.process_id.return_value = 100
    api.window_visible.return_value = True
    presence = GamePresenceMonitor(application, api)
    path = tmp_path / "Launch.log"
    write_login(path)
    store = MatchStore(":memory:")
    widget = MainWindow(store, presence, LocalPlayerLog(path))
    presence.timer.stop()
    widget.local_player_monitor.timer.stop()
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=QMessageBox.StandardButton.Yes))
    yield widget
    widget.close()
    store.close()


def observe(
    window: MainWindow, account: str = "Steam|123|0", guid: str = "live", name: str = "Me"
) -> None:
    window._receive(
        json.dumps(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": guid,
                    "Game": {"PlaylistId": 11},
                    "Players": [
                        {"PrimaryId": account, "Name": name, "TeamNum": 0, "Boost": 90},
                        {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, "Boost": 70},
                        {"PrimaryId": "enemy", "Name": "Enemy", "TeamNum": 1},
                        {"PrimaryId": "enemy2", "Name": "Other", "TeamNum": 1},
                    ],
                },
            }
        )
    )


def test_detection_should_select_and_record_the_account_without_manual_selection(
    window: MainWindow,
) -> None:
    observe(window)
    assert window.matches.player.currentData() == "Steam|123|0"
    assert window.live.player_id == "Steam|123|0"
    assert window.store.setting("player_id") == "Steam|123|0"
    window._receive(
        json.dumps({"Event": "MatchEnded", "Data": {"MatchGuid": "live", "WinnerTeamNum": 0}})
    )
    assert window.store.summary("Steam|123|0").wins == 1
    assert "Steam|123|0" not in window.logs.text.toPlainText()


def test_history_selection_should_not_change_tracking_or_allow_an_opponent_boost_overlay(
    window: MainWindow,
) -> None:
    observe(window)
    window.settings.boost_overlay.scope.setCurrentIndex(2)
    hud = window.boost_overlay.window
    window.matches.player.setCurrentIndex(window.matches.player.findData("enemy"))

    assert window.matches.player.currentData() == "enemy"
    assert window.matches._player_id == "enemy"
    assert window.tracker.player_id == "Steam|123|0"
    assert window.tracker.match_id == "live"
    assert window.live.player_id == "Steam|123|0"
    assert set(window.live.teammate_gauges) == {"mate"}
    assert set(hud.gauges) == {"mate"}
    assert window.store.setting("player_id") == "Steam|123|0"
    window._receive(
        json.dumps({"Event": "MatchEnded", "Data": {"MatchGuid": "live", "WinnerTeamNum": 0}})
    )
    assert window.store.summary("Steam|123|0").wins == 1
    assert window.store.filtered_history("enemy", None, None) == []


def encounter_scope(window: MainWindow, primary_id: str) -> object:
    for row in range(window.live.players.rowCount()):
        item = window.live.players.item(row, 0)
        if item.data(Qt.ItemDataRole.UserRole) == primary_id:
            return item.data(ENCOUNTER_ROLE)
    raise AssertionError(f"Missing live participant: {primary_id}")


def test_scoreboard_should_keep_the_detected_account_when_history_selection_changes(
    window: MainWindow,
) -> None:
    observe(window)
    controls = window.settings.scoreboard_overlay
    controls.players_scope.setCurrentIndex(controls.players_scope.findData("team"))
    controls.enabled.setChecked(True)

    window.matches.player.setCurrentIndex(window.matches.player.findData("enemy"))

    table = window.scoreboard_overlay.window.players
    primary_ids = [
        table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(table.rowCount())
    ]
    assert window.live.player_id == "Steam|123|0"
    assert set(primary_ids) == {None, "Steam|123|0", "mate"}
    assert window.matches._player_id == "enemy"


def test_encounters_should_keep_the_live_session_when_history_filters_change(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Mock()
    clock.now.return_value = datetime.fromisoformat("2026-10-04T20:10:00+00:00")
    monkeypatch.setattr("rocket_lantern.window.datetime", clock)
    snapshot = MatchSnapshot("previous", "2026-10-04T20:00:00+00:00")
    snapshot.players["mate"] = PlayerStats("mate", "Old mate nickname", 1)
    window.store.save_details(snapshot)
    window.store.save(MatchResult("previous", "Steam|123|0", snapshot.observed_at, 13, "win"))

    observe(window)
    assert encounter_scope(window, "mate") == EncounterScope.SESSION
    window.matches.player.setCurrentIndex(window.matches.player.findData("enemy"))
    window._start_session()
    assert encounter_scope(window, "mate") == EncounterScope.SESSION

    window.matches.player.setCurrentIndex(window.matches.player.findData("Steam|123|0"))
    window._start_session()
    assert encounter_scope(window, "mate") == EncounterScope.HISTORY


def test_encounters_should_refresh_when_the_previous_result_is_saved_after_a_new_match_starts(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Mock()
    clock.now.return_value = datetime.fromisoformat("2026-10-04T20:10:00+00:00")
    monkeypatch.setattr("rocket_lantern.window.datetime", clock)

    observe(window, guid="first")
    assert encounter_scope(window, "mate") is None

    observe(window, guid="second")

    assert window.store.history("Steam|123|0")[0]["outcome"] == "unknown"
    assert encounter_scope(window, "mate") == EncounterScope.SESSION


def test_encounters_should_keep_current_session_markers_when_a_match_ends_after_its_last_state(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Mock()
    clock.now.return_value = datetime.fromisoformat("2026-10-04T20:10:00+00:00")
    monkeypatch.setattr("rocket_lantern.window.datetime", clock)
    snapshot = MatchSnapshot("previous", "2026-10-04T20:00:00+00:00")
    snapshot.players["mate"] = PlayerStats("mate", "Mate", 1)
    window.store.save_details(snapshot)
    window.store.save(MatchResult("previous", "Steam|123|0", snapshot.observed_at, 11, "win"))
    observe(window)
    assert encounter_scope(window, "mate") == EncounterScope.SESSION

    clock.now.return_value = datetime.fromisoformat("2026-10-04T20:12:00+00:00")
    window._receive(
        json.dumps({"Event": "MatchEnded", "Data": {"MatchGuid": "live", "WinnerTeamNum": 0}})
    )

    assert encounter_scope(window, "mate") == EncounterScope.SESSION
    assert window.live.state.snapshot.observed_at == "2026-10-04T20:12:00+00:00"


def test_account_switch_should_clear_stale_boosts_and_follow_the_new_account(
    window: MainWindow,
) -> None:
    observe(window)
    window.settings.boost_overlay.scope.setCurrentIndex(2)
    hud = window.boost_overlay.window
    write_login(window.local_player_monitor.source.path, "Epic|abc|0")
    window.local_player_monitor.check()

    assert window.tracker.player_id == "Epic|abc|0"
    assert window.matches.player.currentData() == "Epic|abc|0"
    assert window.live.state.snapshot is None
    assert not hud.isVisible()
    assert window.store.summary("Steam|123|0").unknown == 1
    observe(window, account="Epic|abc|0", guid="next-match")
    assert hud.isVisible()
    assert set(hud.gauges) == {"mate"}
    assert window.store.setting("player_id") == "Epic|abc|0"


def test_logout_should_clear_identity_and_allow_manual_fallback(window: MainWindow) -> None:
    observe(window)
    write_login(window.local_player_monitor.source.path, status="LS_NotLoggedIn")
    window.local_player_monitor.check()
    assert window.tracker.player_id == ""
    assert window.live.player_id == ""
    assert window.matches.player.currentData() == ""

    observe(window)
    window.matches.player.setCurrentIndex(window.matches.player.findData("Steam|123|0"))
    assert window.tracker.player_id == "Steam|123|0"
    assert window.live.player_id == "Steam|123|0"


def test_game_close_should_keep_favorites_browsable_without_reassigning_the_live_account(
    window: MainWindow,
) -> None:
    observe(window)
    window.matches.player.setCurrentIndex(window.matches.player.findData("mate"))
    window.matches.favorite_player.click()
    window.player_favorites.set_favorite("enemy", "Enemy", True)
    window.game_presence.api.game_process_ids.return_value = frozenset()
    window.game_presence._scan_ticks = 0

    window.game_presence.check()
    window.local_player_monitor.check()

    assert window.game_presence.state.running is False
    assert window.matches.player.currentData() == "mate"
    assert window.matches.favorite_player.isChecked()
    assert window.tracker.player_id == ""
    assert window.live.player_id == ""
    assert window.store.setting("player_id") == "Steam|123|0"
    window.matches.player.setCurrentIndex(window.matches.player.findData("enemy"))
    assert window.matches._player_id == "enemy"
    assert window.tracker.player_id == ""
    assert window.live.player_id == ""


def test_duplicate_detection_should_not_interrupt_a_match_or_write_preferences_again(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    observe(window)
    save = Mock(wraps=window.store.set_settings)
    monkeypatch.setattr(window.store, "set_settings", save)
    window.local_player_monitor.check()
    window.local_player_monitor.check()
    assert window.tracker.match_id == "live"
    save.assert_not_called()


def test_api_name_should_repair_detected_name_and_persist_it_without_switching_identity(
    window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window._local_player_changed(LocalPlayer("Steam|123|0", "�ther"))
    save = Mock(wraps=window.store.set_settings)
    monkeypatch.setattr(window.store, "set_settings", save)

    observe(window, name="Æther")

    assert window.selected_name == "Æther"
    assert window.matches.player.currentText() == "Æther"
    assert "Æther" in window.matches.counters.context.text()
    assert window.store.setting("player_name") == "Æther"
    assert window.tracker.player_id == "Steam|123|0"
    assert window.tracker.match_id == "live"
    assert window.live.player_id == "Steam|123|0"
    save.assert_called_once()
    observe(window, name="Æther")
    window._receive(json.dumps({"Event": "MatchDestroyed", "Data": {"MatchGuid": "live"}}))
    window._update_players(force=True)
    assert window.matches.player.currentText() == "Æther"
    save.assert_called_once()


def test_late_account_detection_should_keep_the_matching_api_display_name(
    window: MainWindow,
) -> None:
    observe(window, name="Æther")

    window._local_player_changed(LocalPlayer("Steam|123|0", "�ther"))

    assert window.selected_name == "Æther"
    assert window.store.setting("player_name") == "Æther"
    assert window.matches.player.currentText() == "Æther"
    assert window.tracker.match_id == "live"


def test_api_name_should_not_replace_selected_history_player_with_detected_account(
    window: MainWindow,
) -> None:
    observe(window, name="Æther")
    window.matches.player.setCurrentIndex(window.matches.player.findData("enemy"))

    observe(window, name="Æther 🎮")

    assert window.selected_name == "Enemy"
    assert window.matches.player.currentData() == "enemy"
    assert "Enemy" in window.matches.counters.context.text()
    assert window.store.setting("player_name") == "Æther 🎮"
    assert window.tracker.player_id == "Steam|123|0"
