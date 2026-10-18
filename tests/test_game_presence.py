"""Game lifetime and focus are independent; native access is replaced by a strict fake."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_presence import GamePresence, GamePresenceApi, GamePresenceMonitor


@pytest.fixture
def monitor(application: QApplication) -> Iterator[GamePresenceMonitor]:
    api = Mock(spec=GamePresenceApi)
    api.game_process_ids.return_value = frozenset({100})
    api.foreground_window.return_value = 10
    api.process_id.return_value = 100
    api.window_visible.return_value = True
    owner = QObject(application)
    detector = GamePresenceMonitor(owner, api)
    detector.start()
    detector.timer.stop()
    yield detector
    detector.stop()
    owner.deleteLater()


def test_presence_should_report_running_and_foreground_from_the_same_process_identity(
    monitor: GamePresenceMonitor,
) -> None:
    assert monitor.state == GamePresence(True, True, 10)
    assert monitor.allows_overlay


def test_presence_should_keep_running_but_hide_overlays_after_alt_tab(
    monitor: GamePresenceMonitor,
) -> None:
    monitor.api.process_id.return_value = 200

    monitor.check()

    assert monitor.state == GamePresence(running=True)
    assert not monitor.allows_overlay
    monitor.api.process_id.return_value = 100
    monitor.check()
    assert monitor.allows_overlay


def test_presence_should_keep_running_when_foreground_is_transiently_unavailable(
    monitor: GamePresenceMonitor,
) -> None:
    monitor.api.foreground_window.return_value = 0
    monitor.api.process_id.reset_mock()

    monitor.check()

    assert monitor.state == GamePresence(running=True)
    monitor.api.process_id.assert_not_called()


def test_presence_should_hide_minimized_or_hidden_game_without_reporting_it_closed(
    monitor: GamePresenceMonitor,
) -> None:
    monitor.api.window_visible.return_value = False

    monitor.check()

    assert monitor.state == GamePresence(running=True)


def test_presence_should_bound_process_scans_while_checking_focus_every_poll(
    monitor: GamePresenceMonitor,
) -> None:
    for _ in range(3):
        monitor.check()
    assert monitor.api.game_process_ids.call_count == 1
    assert monitor.api.foreground_window.call_count == 4
    monitor.check()
    assert monitor.api.game_process_ids.call_count == 2
    assert monitor.timer.interval() == 500


def test_presence_should_accept_any_detected_game_instance_without_tracking_other_apps(
    monitor: GamePresenceMonitor,
) -> None:
    monitor.api.game_process_ids.return_value = frozenset({100, 101})
    monitor.api.process_id.return_value = 101
    monitor._scan_ticks = 0

    monitor.check()

    assert monitor.allows_overlay


def test_presence_should_report_absence_only_after_successful_process_scan(
    monitor: GamePresenceMonitor,
) -> None:
    monitor.api.game_process_ids.return_value = frozenset()
    monitor._scan_ticks = 0

    monitor.check()

    assert monitor.state == GamePresence(running=False)


def test_presence_should_report_unknown_not_absent_and_log_repeated_failure_only_once(
    monitor: GamePresenceMonitor, caplog: pytest.LogCaptureFixture
) -> None:
    monitor.api.game_process_ids.side_effect = OSError("Access denied")
    monitor._scan_ticks = 0

    monitor.check()
    monitor.check()

    assert monitor.state == GamePresence()
    assert not monitor.allows_overlay
    assert caplog.text.count("Rocket League detection unavailable") == 1
    monitor.api.game_process_ids.side_effect = None
    monitor.check()
    assert monitor.allows_overlay


def test_presence_should_keep_known_lifetime_when_only_foreground_inspection_fails(
    monitor: GamePresenceMonitor,
) -> None:
    monitor.api.foreground_window.side_effect = OSError("Transient window error")

    monitor.check()

    assert monitor.state == GamePresence(running=True)
    assert not monitor.allows_overlay


def test_presence_should_emit_changes_only_on_transitions_and_poll_for_shared_guards(
    monitor: GamePresenceMonitor,
) -> None:
    changed = Mock()
    polled = Mock()
    monitor.changed.connect(changed)
    monitor.polled.connect(polled)

    monitor.check()
    monitor.check()

    changed.assert_not_called()
    assert polled.call_count == 2
    monitor.api.window_visible.return_value = False
    monitor.check()
    changed.assert_called_once_with(GamePresence(running=True))


def test_presence_should_ignore_late_poll_after_shutdown(monitor: GamePresenceMonitor) -> None:
    monitor.stop()
    monitor.api.game_process_ids.reset_mock()
    monitor.api.foreground_window.reset_mock()

    monitor.check()

    monitor.api.game_process_ids.assert_not_called()
    monitor.api.foreground_window.assert_not_called()
