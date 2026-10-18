"""Account detection shares game presence and reads only test-owned log files."""

import errno
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_presence import GamePresence, GamePresenceMonitor
from rocket_lantern.local_player import LocalPlayer, LocalPlayerLog
from rocket_lantern.local_player_monitor import LocalPlayerMonitor, default_log_path


def write_login(path: Path, account: str = "Steam|123|0") -> None:
    path.write_text(
        "[0001.23] Party: HandleLocalPlayerLoginStatusChanged "
        f"PlayerName=Test PlayerID={account} LoginStatus=LS_LoggedIn "
        "IsPrimary=True IsInParty=False\n",
        encoding="utf-8",
    )


@pytest.fixture
def monitor(application: QApplication, tmp_path: Path) -> Iterator[LocalPlayerMonitor]:
    presence = GamePresenceMonitor(application)
    presence.state = GamePresence(running=True)
    source = LocalPlayerLog(tmp_path / "Launch.log")
    write_login(source.path)
    detector = LocalPlayerMonitor(application, presence, source, clock=lambda: 100.0)
    detector.start()
    detector.timer.stop()
    yield detector
    detector.stop()
    detector.deleteLater()
    presence.deleteLater()


def test_monitor_should_detect_an_already_running_account_and_publish_changes_only(
    monitor: LocalPlayerMonitor,
) -> None:
    assert monitor.player == LocalPlayer("Steam|123|0", "Test")
    changed = Mock()
    monitor.changed.connect(changed)
    monitor.check()
    changed.assert_not_called()

    write_login(monitor.source.path, "Epic|abc|0")
    monitor.check()
    changed.assert_called_once_with(LocalPlayer("Epic|abc|0", "Test"))


def test_monitor_should_forget_closed_game_identity_and_not_read_while_absent(
    monitor: LocalPlayerMonitor, monkeypatch: pytest.MonkeyPatch
) -> None:
    read = Mock(wraps=monitor.source.read)
    monkeypatch.setattr(monitor.source, "read", read)
    monitor.presence.state = GamePresence(running=False)
    monitor.check()
    monitor.check()
    assert monitor.player is None
    read.assert_not_called()


def test_monitor_should_keep_identity_through_alt_tab_and_unknown_presence(
    monitor: LocalPlayerMonitor,
) -> None:
    monitor.presence.state = GamePresence(running=True, foreground=False)
    monitor.check()
    monitor.presence.state = GamePresence()
    monitor.check()
    assert monitor.player == LocalPlayer("Steam|123|0", "Test")


def test_monitor_should_reject_previous_session_log_until_new_game_writes_it(
    monitor: LocalPlayerMonitor,
) -> None:
    path = monitor.source.path
    os.utime(path, (10, 10))
    monitor.presence.state = GamePresence(running=False)
    monitor.check()
    monitor.presence.state = GamePresence(running=True)
    monitor.check()
    assert monitor.player is None
    write_login(path, "Epic|abc|0")
    monitor.check()
    assert monitor.player == LocalPlayer("Epic|abc|0", "Test")


def test_monitor_should_notice_process_replacement_even_without_an_absence_poll(
    monitor: LocalPlayerMonitor,
) -> None:
    monitor.presence._process_ids = frozenset({200})
    os.utime(monitor.source.path, (10, 10))
    monitor.check()
    assert monitor.player is None


def test_monitor_should_report_file_errors_once_without_exposing_log_content(
    monitor: LocalPlayerMonitor, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        monitor.source,
        "read",
        Mock(side_effect=PermissionError(errno.EACCES, "sensitive log content")),
    )
    monitor.check()
    monitor.check()
    assert monitor.player is None
    assert caplog.text.count("Local player log unavailable") == 1
    assert "sensitive log content" not in caplog.text


def test_monitor_should_ignore_late_callbacks_after_shutdown(monitor: LocalPlayerMonitor) -> None:
    monitor.stop()
    write_login(monitor.source.path, "Epic|abc|0")
    monitor.check()
    assert monitor.player == LocalPlayer("Steam|123|0", "Test")
    assert not monitor.timer.isActive()


def test_monitor_should_catch_up_startup_logs_in_bounded_event_loop_turns(
    monitor: LocalPlayerMonitor, application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rocket_lantern.local_player.MAX_READ_BYTES", 80)
    monitor.stop()
    monitor.source.reset()
    monitor.player = None
    monitor.start()
    assert not monitor.source.ready
    assert monitor.timer.interval() == 0
    for _ in range(10):
        application.processEvents()
    assert monitor.player == LocalPlayer("Steam|123|0", "Test")
    assert monitor.source.ready
    assert monitor.timer.interval() == 2000


def test_default_path_should_not_read_host_game_logs_in_offscreen_tests(
    application: QApplication,
) -> None:
    assert default_log_path() is None


def test_default_path_should_use_the_windows_documents_location(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rocket_lantern.local_player_monitor.sys.platform", "win32")
    monkeypatch.setattr(
        "rocket_lantern.local_player_monitor.QGuiApplication.platformName", lambda: "windows"
    )
    monkeypatch.setattr(
        "rocket_lantern.local_player_monitor.QStandardPaths.writableLocation",
        lambda _: str(tmp_path),
    )
    assert default_log_path() == tmp_path / "My Games/Rocket League/TAGame/Logs/Launch.log"
