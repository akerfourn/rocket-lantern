"""Update UI requires confirmation and never launches real installers in tests."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from rocket_lantern import update_controller
from rocket_lantern.i18n import language_manager
from rocket_lantern.storage import MatchStore
from rocket_lantern.updates import RELEASE_URL, UpdateRelease
from rocket_lantern.window import MainWindow


class PendingReply(QObject):
    finished = Signal()
    readyRead = Signal()

    def abort(self) -> None:
        self.finished.emit()


@pytest.fixture
def window(application: QApplication) -> Iterator[MainWindow]:
    store = MatchStore(":memory:")
    widget = MainWindow(store)
    widget.show()
    yield widget
    widget.close()
    widget.deleteLater()
    store.close()


def available(*, unstable: bool = False) -> UpdateRelease:
    return UpdateRelease(
        "2.0.0",
        RELEASE_URL + "tag/v2.0.0",
        unstable,
        RELEASE_URL + "download/v2.0.0/setup.exe",
        "a" * 64,
        100,
    )


def test_update_ui_should_show_notification_without_downloading(window: MainWindow) -> None:
    controller = window.updates
    controller.client.download = Mock()
    controller._checked(available())
    assert controller.button.isVisible()
    assert not controller.button.icon().isNull()
    assert "2.0.0" in controller.button.toolTip()
    controller.client.download.assert_not_called()


def test_update_ui_should_persist_channel_and_warn_for_unstable_without_network(
    window: MainWindow,
) -> None:
    controller = window.updates
    controller.client.manager.get = Mock()
    window.settings.update_channel.setCurrentIndex(window.settings.update_channel.findData("all"))
    assert window.store.setting("update_channel") == "all"
    assert not window.settings.update_warning.isHidden()
    controller._checked(available(unstable=True))
    assert "Préversion" in controller.button.toolTip()
    window.settings.update_channel.setCurrentIndex(0)
    assert window.store.setting("update_channel") == "disabled"
    assert not window.settings.check_updates.isEnabled()
    assert controller.button.isHidden()
    controller.client.manager.get.assert_not_called()


def test_update_ui_should_restore_saved_channel(application: QApplication) -> None:
    store = MatchStore(":memory:")
    store.set_setting("update_channel", "disabled")
    widget = MainWindow(store)
    try:
        assert widget.settings.update_channel.currentData() == "disabled"
        assert widget.updates.client.channel == "disabled"
    finally:
        widget.close()
        store.close()


def test_settings_should_keep_current_version_and_release_link_when_updates_are_disabled(
    window: MainWindow,
) -> None:
    version_label = window.settings.current_version
    release_link = window.settings.release_link
    window.settings.show()

    assert version_label.isVisible()
    assert release_link.isVisible()
    assert window.updates.current in version_label.text()
    assert RELEASE_URL in release_link.text()
    assert release_link.openExternalLinks()

    window.settings.update_channel.setCurrentIndex(
        window.settings.update_channel.findData("disabled")
    )

    assert window.updates.current in version_label.text()
    assert RELEASE_URL in release_link.text()
    assert release_link.openExternalLinks()


def test_update_ui_should_disable_checks_and_cancel_pending_request_when_active(
    window: MainWindow,
) -> None:
    reply = PendingReply()
    controller = window.updates
    controller.client.manager.get = Mock(return_value=reply)
    controller.start()
    window.settings.update_channel.setCurrentIndex(0)
    assert controller.client.channel == "disabled"
    assert not controller.client.timer.isActive()
    assert not window.settings.check_updates.isEnabled()
    controller.client.manager.get.assert_called_once()


def test_update_ui_should_not_download_when_confirmation_is_declined(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update_controller, "can_install", lambda: True)
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.No)
    controller = window.updates
    controller.client.download = Mock()
    controller._checked(available())
    controller.button.click()
    controller.client.download.assert_not_called()
    assert not controller._install_confirmed


def test_update_ui_should_start_download_only_after_confirmation(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update_controller, "can_install", lambda: True)
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    controller = window.updates
    controller.client.download = Mock()
    release = available()
    controller._checked(release)
    controller.button.click()
    controller.client.download.assert_called_once_with(release)
    assert controller._install_confirmed


def test_update_ui_should_open_release_page_for_portable_after_confirmation(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update_controller, "can_install", lambda: False)
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    browser = Mock(return_value=True)
    monkeypatch.setattr(update_controller.QDesktopServices, "openUrl", browser)
    controller = window.updates
    controller.client.download = Mock()
    controller._checked(available())
    controller.button.click()
    controller.client.download.assert_not_called()
    assert browser.call_args.args[0].toString() == available().page_url


def test_update_ui_should_launch_verified_installer_and_close_app_after_download(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(update_controller, "can_install", lambda: True)
    process = Mock(return_value=(True, 123))
    monkeypatch.setattr(update_controller.QProcess, "startDetached", process)
    controller = window.updates
    controller._install("fake-installer.exe")
    process.assert_not_called()
    controller._install_confirmed = True
    monkeypatch.setattr(window, "close", Mock())
    controller._install("fake-installer.exe")
    process.assert_called_once_with(
        "fake-installer.exe", [f"/DIR={Path(update_controller.sys.executable).parent}"]
    )
    window.close.assert_called_once()


def test_update_ui_should_translate_pending_notification_and_settings(
    window: MainWindow, application: QApplication
) -> None:
    controller = window.updates
    controller._checked(available(unstable=True))
    manager = language_manager()
    try:
        manager.set_language("en")
        application.processEvents()
        assert controller.button.toolTip() == "Preview available: 2.0.0"
        assert window.settings.check_updates.text() == "Check now"
        assert window.settings.update_channel.itemText(2) == "All updates (unstable)"
        assert "Current version:" in window.settings.current_version.text()
        assert "View releases" in window.settings.release_link.text()
    finally:
        manager.set_language("fr")


def test_update_ui_should_force_check_from_settings(window: MainWindow) -> None:
    reply = PendingReply()
    window.updates.client.manager.get = Mock(return_value=reply)
    window.settings.check_updates.click()
    window.updates.client.manager.get.assert_called_once()
    assert "api.github.com" in window.updates.client.manager.get.call_args.args[0].url().host()
    window.updates.client.stop()


def test_update_ui_should_disable_manual_check_when_detection_is_disabled(
    window: MainWindow,
) -> None:
    window.settings.update_channel.setCurrentIndex(0)
    window.updates.client.manager.get = Mock()
    window.settings.check_updates.click()
    window.updates.client.manager.get.assert_not_called()
