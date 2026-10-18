"""Use fake window APIs: no real game, foreground changes, timers or process inspection."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_presence import GamePresence, GamePresenceMonitor
from rocket_lantern.overlay_monitor import OverlayMonitor, OverlayWindowApi
from rocket_lantern.windows_overlay import (
    HWND_TOPMOST,
    PROCESS_QUERY_LIMITED_INFORMATION,
    TOPMOST_FLAGS,
    WindowRect,
    WindowsOverlayApi,
    rectangles_overlap,
)


@pytest.fixture
def monitor(application: QApplication) -> Iterator[OverlayMonitor]:
    api = Mock(spec=OverlayWindowApi)
    api.foreground_window.return_value = 10
    api.process_id.return_value = 100
    api.process_name.return_value = "RocketLeague.exe"
    api.window_rect.side_effect = lambda window: (
        (0, 0, 1920, 1080) if window == 10 else (20, 20, 300, 66)
    )
    api.extended_style.return_value = 0x08080028
    api.is_above.return_value = True
    owner = QObject(application)
    guard = OverlayMonitor(api, owner, clock=lambda: datetime(2026, 10, 17, 12, tzinfo=UTC))
    guard.window = 20
    yield guard
    guard.stop()
    owner.deleteLater()


def test_monitor_should_use_shared_presence_without_own_timer_or_process_inspection(
    application: QApplication,
) -> None:
    owner = QObject(application)
    presence = GamePresenceMonitor(owner)
    presence.state = GamePresence(True, True, 10)
    api = Mock(spec=OverlayWindowApi)
    api.window_rect.return_value = (0, 0, 1920, 1080)
    api.is_above.return_value = True
    guard = OverlayMonitor(api, owner, presence=presence)
    try:
        guard.start(20)
        assert not guard.timer.isActive()
        api.foreground_window.assert_not_called()
        api.process_id.assert_not_called()
        api.process_name.assert_not_called()
        api.promote.assert_called_once_with(20)
        api.window_rect.reset_mock()
        presence.polled.emit()
        assert api.window_rect.call_count == 2
        presence.state = GamePresence(running=True)
        api.window_rect.reset_mock()
        presence.polled.emit()
        api.window_rect.assert_not_called()
        guard.stop()
        presence.state = GamePresence(True, True, 10)
        presence.polled.emit()
        api.window_rect.assert_not_called()
    finally:
        guard.stop()
        owner.deleteLater()


def test_monitor_should_promote_only_overlay_when_game_takes_foreground(
    monitor: OverlayMonitor,
) -> None:
    monitor.api.is_above.side_effect = [False, True]

    monitor.check()

    monitor.api.promote.assert_called_once_with(20)
    assert monitor.observation.above_before is False
    assert monitor.observation.above_after is True
    assert monitor.observation.placement_requests == 1
    assert monitor.observation.observed_at == "2026-10-17T12:00:00+00:00"


def test_monitor_should_not_repeat_placement_while_order_is_already_correct(
    monitor: OverlayMonitor,
) -> None:
    monitor.check()
    monitor.check()
    monitor.check()

    monitor.api.promote.assert_called_once_with(20)
    monitor.api.process_name.assert_called_once_with(100)


def test_monitor_should_restore_order_if_game_moves_above_overlay_again(
    monitor: OverlayMonitor,
) -> None:
    monitor.check()
    monitor.api.is_above.side_effect = [False, True]

    monitor.check()

    assert monitor.api.promote.call_count == 2
    assert monitor.observation.placement_requests == 2
    assert monitor.observation.above_after is True


def test_monitor_should_not_touch_other_apps_and_keep_last_game_observation(
    monitor: OverlayMonitor,
) -> None:
    monitor.check()
    original = monitor.observation.diagnostic()
    monitor.api.foreground_window.return_value = 30
    monitor.api.process_id.return_value = 200
    monitor.api.process_name.return_value = "another-app.exe"
    monitor.api.promote.reset_mock()

    monitor.check()

    monitor.api.promote.assert_not_called()
    assert monitor.observation.diagnostic() == original
    assert "another-app" not in str(monitor.observation.diagnostic())


def test_monitor_should_retry_unreadable_identity_without_requesting_elevation(
    monitor: OverlayMonitor,
) -> None:
    monitor.api.process_name.side_effect = [None, "ROCKETLEAGUE.EXE"]
    monitor.check()
    monitor.api.promote.assert_not_called()

    monitor.check()

    monitor.api.promote.assert_called_once_with(20)


def test_monitor_should_recheck_identity_when_foreground_handle_is_reused(
    monitor: OverlayMonitor,
) -> None:
    monitor.check()
    monitor.api.process_id.return_value = 200
    monitor.api.process_name.return_value = "another-app.exe"
    monitor.api.promote.reset_mock()

    monitor.check()

    monitor.api.promote.assert_not_called()
    assert monitor.api.process_name.call_count == 2


def test_monitor_should_report_failed_native_request_without_claiming_success(
    monitor: OverlayMonitor,
) -> None:
    monitor.api.is_above.return_value = False
    monitor.api.promote.side_effect = OSError("access denied")
    statuses = []
    monitor.status_changed.connect(statuses.append)

    monitor.check()

    assert monitor.observation.error == "access denied"
    assert monitor.observation.above_after is False
    assert monitor.observation.placement_requests == 0
    assert "Échec" in str(statuses[-1])


def test_monitor_should_report_overlay_outside_game_even_when_order_is_correct(
    monitor: OverlayMonitor,
) -> None:
    monitor.api.window_rect.side_effect = lambda window: (
        (0, 0, 1920, 1080) if window == 10 else (-1900, 20, -1600, 66)
    )
    statuses = []
    monitor.status_changed.connect(statuses.append)

    monitor.check()

    assert monitor.observation.overlaps_game is False
    assert "hors de la fenêtre" in str(statuses[-1])


def test_monitor_should_stop_all_native_calls_when_disabled(monitor: OverlayMonitor) -> None:
    monitor.start(20)
    assert monitor.timer.isActive()
    monitor.stop()
    monitor.api.reset_mock()

    monitor.check()

    assert not monitor.timer.isActive()
    monitor.api.foreground_window.assert_not_called()


@pytest.mark.parametrize(
    ("first", "second", "overlap"),
    [
        ((-1920, 0, 0, 1080), (-1900, 20, -1600, 66), True),
        ((0, 0, 1920, 1080), (-1900, 20, -1600, 66), False),
        ((0, 0, 100, 100), (100, 0, 200, 100), False),
    ],
)
def test_rectangles_should_handle_negative_monitor_coordinates(
    first: WindowRect, second: WindowRect, overlap: bool
) -> None:
    assert rectangles_overlap(first, second) is overlap


def test_native_api_should_use_nonactivating_flags_and_modify_only_requested_window() -> None:
    api = object.__new__(WindowsOverlayApi)
    api.user32 = Mock()

    api.promote(123)

    api.user32.SetWindowPos.assert_called_once_with(123, HWND_TOPMOST, 0, 0, 0, 0, TOPMOST_FLAGS)
    assert TOPMOST_FLAGS & 0x0010  # SWP_NOACTIVATE
    assert TOPMOST_FLAGS & 0x0200  # SWP_NOOWNERZORDER


@pytest.mark.parametrize("windows, expected", [([20, 10], True), ([10, 20], False), ([10], None)])
def test_native_api_should_distinguish_unknown_order_from_overlay_behind_game(
    windows: list[int], expected: bool | None
) -> None:
    api = object.__new__(WindowsOverlayApi)
    api._enum_callback = lambda callback: callback
    api.user32 = Mock()

    def enumerate_windows(callback: Callable[[int, int], bool], parameter: int) -> None:
        for window in windows:
            if not callback(window, parameter):
                break

    api.user32.EnumWindows.side_effect = enumerate_windows

    assert api.is_above(20, 10) is expected


@pytest.mark.parametrize("readable", [True, False])
def test_native_api_should_close_identity_handle_even_if_query_fails(readable: bool) -> None:
    api = object.__new__(WindowsOverlayApi)
    api.kernel32 = Mock()
    api.kernel32.OpenProcess.return_value = 42

    def query_name(process: int, flags: int, buffer: object, length: object) -> bool:
        buffer.value = r"C:\Games\RocketLeague.exe"
        return readable

    api.kernel32.QueryFullProcessImageNameW.side_effect = query_name

    name = api.process_name(100)

    assert name == ("RocketLeague.exe" if readable else None)
    api.kernel32.OpenProcess.assert_called_once_with(PROCESS_QUERY_LIMITED_INFORMATION, False, 100)
    api.kernel32.CloseHandle.assert_called_once_with(42)
