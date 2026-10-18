"""Shared presence gates both HUDs, but connection lifetime is independent of focus."""

import json
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from rocket_lantern.game_presence import GamePresenceApi, GamePresenceMonitor
from rocket_lantern.storage import MatchStore
from rocket_lantern.window import MainWindow


@pytest.fixture
def window(application: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    api = Mock(spec=GamePresenceApi)
    api.game_process_ids.return_value = frozenset()
    api.foreground_window.return_value = 10
    api.process_id.return_value = 100
    api.window_visible.return_value = True
    presence = GamePresenceMonitor(application, api)
    store = MatchStore(":memory:")
    store.set_setting("player_id", "me")
    widget = MainWindow(store, presence)
    presence.timer.stop()
    monkeypatch.setattr(widget.client.socket, "open", Mock())
    monkeypatch.setattr(QMessageBox, "warning", Mock(return_value=QMessageBox.StandardButton.Yes))
    yield widget
    widget.close()
    store.close()


def set_game_running(window: MainWindow, running: bool = True) -> None:
    process_ids = frozenset()
    if running:
        process_ids = frozenset({100})
    window.game_presence.api.game_process_ids.return_value = process_ids
    window.game_presence._scan_ticks = 0
    window.game_presence.check()


def observe(window: MainWindow) -> None:
    window._receive(
        json.dumps(
            {
                "Event": "UpdateState",
                "Data": {
                    "MatchGuid": "live",
                    "Game": {"PlaylistId": 11},
                    "Players": [
                        {"PrimaryId": "me", "Name": "Me", "TeamNum": 0, "Boost": 90},
                        {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, "Boost": 75},
                        {"PrimaryId": "other", "Name": "Other", "TeamNum": 1},
                    ],
                },
            }
        )
    )


def test_connection_should_wait_without_socket_attempts_until_game_launch(
    window: MainWindow,
) -> None:
    window.start()

    assert not window.client.is_running
    assert not window.client.retry.isActive()
    assert not window.client.timeout.isActive()
    window.client.socket.open.assert_not_called()
    assert window.status.text() == "En attente de Rocket League…"
    set_game_running(window)
    assert window.client.is_running
    window.client.socket.open.assert_called_once()


def test_connection_should_keep_recording_through_focus_loss_and_minimization(
    window: MainWindow,
) -> None:
    set_game_running(window)
    window.start()
    observe(window)
    snapshot = window.live.state.snapshot
    window.game_presence.api.process_id.return_value = 200

    window.game_presence.check()

    assert window.client.is_running
    assert window.live.state.snapshot is snapshot
    window.game_presence.api.process_id.return_value = 100
    window.game_presence.api.window_visible.return_value = False
    window.game_presence.check()
    assert window.client.is_running
    assert window.live.state.snapshot is snapshot
    window.client.socket.open.assert_called_once()


def test_connection_should_stop_retries_clear_live_data_and_resume_after_game_restart(
    window: MainWindow,
) -> None:
    set_game_running(window)
    window.start()
    observe(window)
    assert window.live.state.snapshot is not None
    window.client.retry.start(3000)

    set_game_running(window, False)

    assert not window.client.is_running
    assert not window.client.retry.isActive()
    assert window.live.state.snapshot is None
    assert window.status.text() == "En attente de Rocket League…"
    set_game_running(window)
    assert window.client.is_running
    assert window.client.socket.open.call_count == 2


def test_connection_should_use_latest_configured_port_when_game_starts(window: MainWindow) -> None:
    window.port.setValue(50100)
    window.start()

    set_game_running(window)

    assert window.client.port == 50100
    url = window.client.socket.open.call_args.args[0]
    assert url.port() == 50100


def test_detection_failure_should_not_interrupt_an_active_connection(window: MainWindow) -> None:
    set_game_running(window)
    window.start()
    observe(window)
    snapshot = window.live.state.snapshot
    window.game_presence.api.game_process_ids.side_effect = OSError("Scan failed")
    window.game_presence._scan_ticks = 0

    window.game_presence.check()

    assert window.client.is_running
    assert window.live.state.snapshot is snapshot
    window.client.socket.open.assert_called_once()


def test_overlays_should_hide_on_alt_tab_without_changing_preferences_or_live_data(
    window: MainWindow,
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    window.settings.boost_overlay.scope.setCurrentIndex(2)
    assert window.overlay.window is None
    assert window.boost_overlay.window is None
    set_game_running(window)
    window.start()
    observe(window)
    summary = window.overlay.window
    boosts = window.boost_overlay.window
    snapshot = window.live.state.snapshot
    assert summary.isVisible() and boosts.isVisible()
    assert window.overlay.presence is window.boost_overlay.presence is window.game_presence

    window.game_presence.api.process_id.return_value = 200
    window.game_presence.check()

    assert not summary.isVisible() and not boosts.isVisible()
    assert window.settings.overlay.enabled.isChecked()
    assert window.settings.boost_overlay.activation_enabled()
    assert window.store.setting("overlay_enabled") == "1"
    assert window.store.setting("boost_overlay_mode") == "all"
    assert window.live.state.snapshot is snapshot
    observe(window)
    assert not boosts.isVisible(), "A telemetry packet must not bypass the foreground gate"
    window.game_presence.api.process_id.return_value = 100
    window.game_presence.check()
    assert summary.isVisible() and boosts.isVisible()


def test_overlay_editor_should_remain_available_without_game_and_not_show_hud_after_save(
    window: MainWindow,
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    window.settings.overlay.place_button.click()

    editor = window.overlay.editor
    assert editor.isVisible()
    editor.save_button.click()
    assert window.overlay.window is None
    assert window.settings.overlay.enabled.isChecked()


def test_focus_return_should_not_restore_expired_teammate_boost(window: MainWindow) -> None:
    set_game_running(window)
    window.settings.boost_overlay.scope.setCurrentIndex(2)
    observe(window)
    boosts = window.boost_overlay.window
    window.game_presence.api.process_id.return_value = 200
    window.game_presence.check()
    window.boost_overlay._expire()

    window.game_presence.api.process_id.return_value = 100
    window.game_presence.check()

    assert not boosts.isVisible()
    observe(window)
    assert boosts.isVisible()


def test_close_should_stop_shared_detector_and_prevent_late_reconnect(window: MainWindow) -> None:
    window.start()

    window.close()
    set_game_running(window)

    assert not window.game_presence.timer.isActive()
    assert not window.client.is_running
    window.client.socket.open.assert_not_called()


def test_manual_reconnect_should_remain_available_when_game_detection_is_unknown(
    window: MainWindow,
) -> None:
    window.game_presence.api.game_process_ids.side_effect = OSError("Scan failed")
    window.game_presence._scan_ticks = 0
    window.game_presence.check()
    window.client.socket.open.assert_not_called()

    window.start()

    assert window.game_presence.state.running is None
    assert window.client.is_running
    window.client.socket.open.assert_called_once()


def test_restored_overlay_preferences_should_wait_for_game_focus_without_showing_on_desktop(
    window: MainWindow, application: QApplication
) -> None:
    window.settings.overlay.enabled.setChecked(True)
    window.settings.boost_overlay.scope.setCurrentIndex(2)
    presence = GamePresenceMonitor(application, window.game_presence.api)
    restored = MainWindow(window.store, presence)
    presence.timer.stop()
    try:
        assert restored.settings.overlay.enabled.isChecked()
        assert restored.settings.boost_overlay.activation_enabled()
        assert restored.overlay.window is None
        assert restored.boost_overlay.window is None
        set_game_running(restored)
        observe(restored)
        assert restored.overlay.window.isVisible()
        assert restored.boost_overlay.window.isVisible()
    finally:
        restored.close()
