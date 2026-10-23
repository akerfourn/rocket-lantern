"""Live scoreboard HUD: independent preferences, filtering, freshness and placement."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_presence import GamePresence
from rocket_lantern.i18n import language_manager
from rocket_lantern.live_team_table import LiveTeamTable
from rocket_lantern.overlay_placement import OverlayPlacement, parse_placement
from rocket_lantern.scoreboard_overlay import ScoreboardOverlay
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow

OBSERVED_AT = "2026-10-23T19:00:00+00:00"


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    widget.live.set_player("me")
    yield widget
    widget.close()
    store.close()
    language_manager().set_language("fr")


def observe(window: MainWindow, *, boost: int = 60, team: int = 0) -> None:
    window.live.observe(
        {
            "Event": "UpdateState",
            "Data": {
                "MatchGuid": "live",
                "Game": {"PlaylistId": 13},
                "Players": [
                    {
                        "PrimaryId": "me",
                        "Name": "Same",
                        "TeamNum": team,
                        "Score": 300,
                        "Goals": 2,
                        "Assists": 1,
                        "Saves": 3,
                        "Shots": 5,
                    },
                    {
                        "PrimaryId": "mate",
                        "Name": "Mate",
                        "TeamNum": 0,
                        "Score": 200,
                        "Goals": 1,
                        "Assists": 2,
                        "Saves": 1,
                        "Boost": boost,
                    },
                    {"PrimaryId": "enemy", "Name": "Same", "TeamNum": 1, "Score": 400},
                    {"PrimaryId": "enemy2", "Name": "Comet", "TeamNum": 1, "Score": 100},
                ],
            },
        },
        OBSERVED_AT,
        False,
    )


def enable(window: MainWindow) -> ScoreboardOverlay:
    window.settings.scoreboard_overlay.enabled.setChecked(True)
    hud = window.scoreboard_overlay.window
    assert isinstance(hud, ScoreboardOverlay)
    return hud


def set_scope(window: MainWindow, scope: str) -> None:
    control = window.settings.scoreboard_overlay.players_scope
    control.setCurrentIndex(control.findData(scope))


def participant_ids(table: LiveTeamTable) -> list[str]:
    result = []
    for row in range(table.rowCount()):
        primary_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if primary_id is not None:
            result.append(primary_id)
    return result


def test_scoreboard_should_start_disabled_and_wait_for_data_after_activation(
    window: MainWindow,
) -> None:
    assert not window.settings.scoreboard_overlay.activation_enabled()
    assert window.scoreboard_overlay.window is None
    window.settings.scoreboard_overlay.enabled.setChecked(True)
    assert window.scoreboard_overlay.window is None

    observe(window)

    assert window.scoreboard_overlay.window.isVisible()
    assert window.store.setting("scoreboard_overlay_enabled") == "1"
    assert not window.settings.overlay.activation_enabled()
    assert not window.settings.boost_overlay.activation_enabled()


def test_scoreboard_should_show_icons_team_totals_and_sorted_players_without_capturing_input(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)
    table = hud.players

    assert table.rowCount() == 7
    assert participant_ids(table) == ["me", "mate", "enemy", "enemy2"]
    assert table.item(0, 0).text() == "Équipe bleue"
    assert table.item(4, 0).text() == "Équipe orange"
    assert table.item(0, 1).text() == table.item(4, 1).text() == "500"
    assert table.item(1, 0).font().bold()
    assert table.columnCount() == 10
    assert all(not table.horizontalHeaderItem(column).icon().isNull() for column in range(1, 10))
    assert hud.isVisible()
    assert hud.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert hud.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert hud.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert hud.parent() is None


def test_scoreboard_filters_should_apply_immediately_and_keep_only_relevant_totals(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)
    snapshot = window.live.state.snapshot

    set_scope(window, "team")
    assert participant_ids(hud.players) == ["me", "mate"]
    assert hud.players.rowCount() == 3
    assert hud.players.item(0, 1).text() == "500"

    set_scope(window, "opponents")
    assert participant_ids(hud.players) == ["enemy", "enemy2"]
    assert hud.players.item(0, 0).text() == "Équipe orange"
    assert hud.players.item(0, 1).text() == "500"

    set_scope(window, "player")
    assert participant_ids(hud.players) == ["me"]
    assert hud.players.rowCount() == 1, "A single player must not masquerade as a whole team"
    assert hud.players.item(0, 1).text() == "300"
    assert window.store.setting("scoreboard_overlay_scope") == "player"
    assert window.live.state.snapshot is snapshot


def test_scoreboard_should_follow_account_and_team_changes_without_reactivation(
    window: MainWindow,
) -> None:
    observe(window)
    set_scope(window, "team")
    hud = enable(window)

    observe(window, team=1)
    assert participant_ids(hud.players) == ["enemy", "me", "enemy2"]
    assert hud.players.item(0, 0).text() == "Équipe orange"
    assert hud.players.item(0, 1).text() == "800"

    window.live.set_player("mate")
    assert participant_ids(hud.players) == ["mate"]
    assert hud.players.item(0, 0).text() == "Équipe bleue"


def test_relative_filters_should_hide_when_identity_is_missing_but_all_players_remain_available(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)
    window.live.set_player("not-in-match")

    for scope in ("team", "opponents", "player"):
        set_scope(window, scope)
        assert not hud.isVisible()
        assert participant_ids(hud.players) == []
    set_scope(window, "all")
    assert hud.isVisible()
    assert len(participant_ids(hud.players)) == 4


def test_scoreboard_should_reuse_rows_and_native_monitor_for_boost_only_updates(
    window: MainWindow, application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    start_monitor = Mock()
    monkeypatch.setattr(window.scoreboard_overlay, "_start_monitor", start_monitor)
    observe(window)
    hud = enable(window)
    application.processEvents()
    application.processEvents()
    player = hud.players.item(1, 0)
    fit = Mock(wraps=hud._fit_table)
    monkeypatch.setattr(hud, "_fit_table", fit)

    observe(window, boost=20)
    observe(window, boost=10)

    assert hud.players.item(1, 0) is player
    fit.assert_not_called()
    start_monitor.assert_called_once()


def test_scoreboard_should_update_event_counters_without_waiting_for_a_new_state(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)

    window.live.observe(
        {
            "Event": "StatfeedEvent",
            "Data": {
                "MatchGuid": "live",
                "EventName": "EpicSave",
                "MainTarget": {"PrimaryId": "me"},
            },
        },
        OBSERVED_AT,
        False,
    )
    assert hud.players.item(0, 4).text() == "4 (1)"
    assert hud.players.item(1, 4).text() == "3 (1)"
    window.live.observe(
        {
            "Event": "CrossbarHit",
            "Data": {
                "MatchGuid": "live",
                "BallLocation": {"X": 890, "Y": 5120, "Z": 500},
                "BallLastTouch": {"Player": {"PrimaryId": "me", "TeamNum": 0}},
            },
        },
        OBSERVED_AT,
        False,
    )
    assert hud.players.item(0, 5).text() == hud.players.item(1, 5).text() == "1"


def test_scoreboard_should_expire_without_clock_or_scope_changes_reviving_stale_stats(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)
    assert window.scoreboard_overlay._expiry.interval() == 3000

    window.scoreboard_overlay._expiry.timeout.emit()
    assert not hud.isVisible()
    window.live.observe(
        {"Event": "ClockUpdatedSeconds", "Data": {"MatchGuid": "live", "TimeSeconds": 100}},
        OBSERVED_AT,
        False,
    )
    set_scope(window, "team")
    assert not hud.isVisible()
    observe(window)
    assert hud.isVisible()


def test_scoreboard_should_hide_on_disconnect_and_clear_departed_match_players(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)
    window._connection_lost()
    assert not hud.isVisible()
    assert hud.players.rowCount() == 0
    assert not window.scoreboard_overlay._expiry.isActive()

    observe(window)
    assert hud.isVisible()
    window.live.observe(
        {"Event": "MatchDestroyed", "Data": {"MatchGuid": "live"}}, OBSERVED_AT, False
    )
    assert not hud.isVisible()
    assert hud.players.rowCount() == 0


def test_scoreboard_should_follow_the_shared_foreground_detector_without_disabling_the_preference(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)
    presence = window.game_presence
    assert window.scoreboard_overlay.presence is presence
    presence.supported = True
    presence.state = GamePresence(running=True)
    presence.changed.emit(presence.state)
    assert not hud.isVisible()
    assert window.settings.scoreboard_overlay.activation_enabled()

    presence.state = GamePresence(True, True, 10)
    presence.changed.emit(presence.state)
    assert hud.isVisible()


def test_scoreboard_should_restore_its_independent_preferences_without_writing_on_startup(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "scoreboard.sqlite3"
    store = MatchStore(path)
    original = MainWindow(store)
    original.settings.scoreboard_overlay.enabled.setChecked(True)
    set_scope(original, "opponents")
    original.settings.scoreboard_overlay.opacity.setValue(65)
    original.settings.scoreboard_overlay.corner.setCurrentIndex(3)
    original.close()
    store.close()

    restored_store = MatchStore(path)
    saved = Mock(wraps=restored_store.set_settings)
    monkeypatch.setattr(restored_store, "set_settings", saved)
    restored = MainWindow(restored_store)
    try:
        assert restored.settings.scoreboard_overlay.activation_enabled()
        assert restored.settings.scoreboard_overlay.players_scope.currentData() == "opponents"
        assert restored.settings.scoreboard_overlay.opacity.value() == 65
        assert restored.scoreboard_overlay._placement.corner == "bottom_right"
        assert restored.scoreboard_overlay.window is None, "Restoring must still wait for live data"
        assert not restored.settings.overlay.activation_enabled()
        assert not restored.settings.boost_overlay.activation_enabled()
        saved.assert_not_called()
        restored.live.set_player("me")
        observe(restored)
        hud = restored.scoreboard_overlay.window
        assert participant_ids(hud.players) == ["enemy", "enemy2"]
        assert hud.windowOpacity() == pytest.approx(0.65, abs=0.01)
    finally:
        restored.close()
        restored_store.close()


def test_scoreboard_should_restore_explicitly_disabled_activation(window: MainWindow) -> None:
    window.settings.scoreboard_overlay.enabled.setChecked(True)
    window.settings.scoreboard_overlay.enabled.setChecked(False)
    restored = MainWindow(window.store)
    try:
        observe(restored)
        assert not restored.settings.scoreboard_overlay.activation_enabled()
        assert restored.scoreboard_overlay.window is None
    finally:
        restored.close()


def test_scoreboard_should_report_and_revert_a_scope_change_when_saving_fails(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    observe(window)
    hud = enable(window)
    failed = Mock()
    window.scoreboard_overlay.failed.disconnect()
    window.scoreboard_overlay.failed.connect(failed)
    monkeypatch.setattr(
        window.store, "set_setting", Mock(side_effect=sqlite3.OperationalError("locked"))
    )

    set_scope(window, "opponents")

    failed.assert_called_once()
    assert window.settings.scoreboard_overlay.players_scope.currentData() == "all"
    assert len(participant_ids(hud.players)) == 4


def test_scoreboard_should_ignore_invalid_saved_scope_without_overwriting_it(
    window: MainWindow, caplog: pytest.LogCaptureFixture
) -> None:
    window.store.set_setting("scoreboard_overlay_scope", "unknown-future-filter")
    restored = MainWindow(window.store)
    try:
        assert restored.settings.scoreboard_overlay.players_scope.currentData() == "all"
        assert "invalid saved scoreboard overlay scope" in caplog.text
        assert window.store.setting("scoreboard_overlay_scope") == "unknown-future-filter"
    finally:
        restored.close()


def test_scoreboard_should_allow_fictional_preview_and_save_placement_while_disabled(
    window: MainWindow,
) -> None:
    controls = window.settings.scoreboard_overlay
    controls.opacity.setValue(45)
    controls.place_button.click()
    editor = window.scoreboard_overlay.editor
    assert editor is not None
    assert len(participant_ids(editor.preview.display.players)) == 4
    assert editor.preview.display.windowOpacity() == 1, "Preview opacity belongs to its wrapper"
    assert editor.preview.opacity_effect.opacity() == 0.45
    set_scope(window, "player")
    assert participant_ids(editor.preview.display.players) == ["preview-me"]
    assert editor.preview.display.players.rowCount() == 1
    editor.preview.place(QPoint(130, 170))
    editor.save_button.click()

    saved = parse_placement(window.store.setting("scoreboard_overlay_placement"))
    assert saved.x_ratio is not None
    assert window.store.setting("overlay_placement") == ""
    assert window.store.setting("boost_overlay_placement") == ""
    assert not controls.activation_enabled()
    assert window.scoreboard_overlay.window is None


def test_scoreboard_should_restore_live_display_after_placement_is_cancelled(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)
    window.settings.scoreboard_overlay.place_button.click()
    assert not hud.isVisible()

    window.scoreboard_overlay.editor.cancel_button.click()

    assert hud.isVisible()
    assert window.store.setting("scoreboard_overlay_placement") == ""


def test_scoreboard_should_fit_every_row_without_scrollbars_and_keep_its_right_anchor(
    window: MainWindow, application: QApplication
) -> None:
    observe(window)
    hud = enable(window)
    window.scoreboard_overlay._set_placement(
        OverlayPlacement(x_ratio=0.95, y_ratio=0.2, horizontal_anchor="right")
    )
    application.processEvents()
    right = hud.x() + hud.width()

    set_scope(window, "player")
    application.processEvents()

    assert hud.x() + hud.width() == right
    table = hud.players
    assert table.viewport().height() >= table.verticalHeader().length()
    assert table.viewport().width() >= table.horizontalHeader().length()
    assert not table.horizontalScrollBar().isVisible()
    assert not table.verticalScrollBar().isVisible()


def test_scoreboard_should_translate_in_place_without_resetting_scope_or_match_data(
    window: MainWindow, application: QApplication
) -> None:
    observe(window)
    set_scope(window, "team")
    hud = enable(window)
    player = hud.players.item(1, 0)
    snapshot = window.live.state.snapshot
    language_manager().set_language("en")
    application.processEvents()

    assert window.settings.overlay_tabs.tabText(2) == "Scoreboard"
    assert window.settings.scoreboard_overlay.players_scope.currentText() == "My team"
    assert hud.windowTitle() == "RocketLantern · Scoreboard"
    assert hud.players.item(0, 0).text() == "Blue team"
    assert hud.players.item(1, 0) is player
    assert player.text() == "Same"
    assert window.live.state.snapshot is snapshot


def test_scoreboard_should_stop_its_timer_and_close_editor_and_window_on_shutdown(
    window: MainWindow,
) -> None:
    observe(window)
    hud = enable(window)
    window.settings.scoreboard_overlay.place_button.click()

    window.close()

    assert not hud.isVisible()
    assert window.scoreboard_overlay.window is None
    assert window.scoreboard_overlay.editor is None
    assert not window.scoreboard_overlay._expiry.isActive()
    observe(window)
    assert window.scoreboard_overlay.window is None, (
        "Late state events must not reopen a closed HUD"
    )
