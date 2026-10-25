"""Startup recovery checks and installation work without SQLite, using fake network replies."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QByteArray, QObject, QStandardPaths, Signal
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication, QMessageBox

from rocket_lantern import storage, update_controller
from rocket_lantern.i18n import language_manager
from rocket_lantern.startup_error_dialog import StartupErrorDialog, StartupStage
from rocket_lantern.storage_errors import NewerDatabaseSchemaError
from rocket_lantern.updates import API_URL, RELEASE_URL, UpdateRelease


class FakeReply(QObject):
    readyRead = Signal()
    finished = Signal()

    def __init__(self, body: bytes = b"[]") -> None:
        super().__init__()
        self.body = body
        self.aborted = False

    def error(self) -> QNetworkReply.NetworkError:
        if self.aborted:
            return QNetworkReply.NetworkError.OperationCanceledError
        return QNetworkReply.NetworkError.NoError

    def errorString(self) -> str:
        return "Simulated failure"

    def readAll(self) -> QByteArray:
        body = self.body
        self.body = b""
        return QByteArray(body)

    def bytesAvailable(self) -> int:
        return len(self.body)

    def abort(self) -> None:
        self.aborted = True
        self.finished.emit()


@pytest.fixture
def dialog(application: QApplication) -> Iterator[StartupErrorDialog]:
    language_manager().set_language("fr")
    widget = StartupErrorDialog(
        StartupStage.DATABASE, NewerDatabaseSchemaError(7, 6), Path("matches.sqlite3")
    )
    widget.updates.client.manager.get = Mock(return_value=FakeReply())
    widget.show()
    yield widget
    widget.close()
    language_manager().set_language("fr")


def available(*, unstable: bool = False, payload: bytes = b"verified installer") -> UpdateRelease:
    version = "2.0.0"
    if unstable:
        version = "2.0.0-alpha.1"
    return UpdateRelease(
        version,
        RELEASE_URL + f"tag/v{version}",
        unstable,
        RELEASE_URL + f"download/v{version}/RocketLantern-{version}-windows-x64-setup.exe",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )


def test_recovery_should_wait_for_a_manual_check_and_keep_diagnostics_available(
    dialog: StartupErrorDialog,
) -> None:
    assert dialog.updates.store is None
    assert dialog.update_panel.update_channel.currentData() == "stable"
    assert dialog.update_panel.check_updates.isEnabled()
    assert dialog.update_panel.install_update.isHidden()
    assert dialog.update_panel.release_link.openExternalLinks()
    assert RELEASE_URL in dialog.update_panel.release_link.text()
    assert not dialog.updates.client.timer.isActive()
    assert "version plus récente" in dialog.hint.text()
    assert "préversions" in dialog.hint.text()
    assert "schema 7" in dialog.details.toPlainText()
    dialog.updates.client.manager.get.assert_not_called()


def test_recovery_should_construct_without_any_database_connection(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_access = Mock(side_effect=AssertionError("Recovery must not open SQLite"))
    monkeypatch.setattr(storage.sqlite3, "connect", database_access)

    widget = StartupErrorDialog(StartupStage.DATABASE, NewerDatabaseSchemaError(7, 6), None)
    try:
        assert widget.updates.store is None
        assert widget.update_panel.check_updates.isEnabled()
        database_access.assert_not_called()
    finally:
        widget.close()


def test_recovery_should_find_previews_without_opening_or_writing_the_database(
    dialog: StartupErrorDialog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_access = Mock(side_effect=AssertionError("Recovery must not open SQLite"))
    monkeypatch.setattr(storage.sqlite3, "connect", database_access)
    reply = FakeReply(
        json.dumps(
            [
                {
                    "draft": False,
                    "prerelease": True,
                    "tag_name": "v2.0.0-alpha.1",
                    "html_url": RELEASE_URL + "tag/v2.0.0-alpha.1",
                    "assets": [],
                }
            ]
        ).encode()
    )
    dialog.updates.client.manager.get.return_value = reply
    controls = dialog.update_panel
    controls.update_channel.setCurrentIndex(controls.update_channel.findData("all"))
    assert not controls.update_warning.isHidden()
    dialog.updates.client.manager.get.assert_not_called()

    controls.check_updates.click()
    reply.finished.emit()

    assert dialog.updates.release.version == "2.0.0-alpha.1"
    assert "Préversion disponible" in controls.update_status.text()
    assert controls.install_update.isVisible()
    assert dialog.updates.button.isHidden(), "Recovery must not create a floating notification"
    assert dialog.updates.button.parentWidget() is dialog
    assert "téléchargement" in controls.install_update.text()
    request = dialog.updates.client.manager.get.call_args.args[0]
    assert request.url().toString().startswith(API_URL)
    assert not dialog.updates.client.timer.isActive()
    database_access.assert_not_called()


def test_recovery_should_filter_previews_when_only_stable_updates_are_selected(
    dialog: StartupErrorDialog,
) -> None:
    reply = FakeReply(
        json.dumps(
            [
                {
                    "draft": False,
                    "prerelease": True,
                    "tag_name": "v2.0.0-alpha.1",
                    "html_url": RELEASE_URL + "tag/v2.0.0-alpha.1",
                    "assets": [],
                }
            ]
        ).encode()
    )
    dialog.updates.client.manager.get.return_value = reply

    dialog.update_panel.check_updates.click()
    reply.finished.emit()

    assert dialog.updates.release is None
    assert dialog.update_panel.update_status.text() == "Aucune mise à jour disponible."
    assert dialog.update_panel.install_update.isHidden()


def test_recovery_should_report_failure_and_allow_retry_without_losing_the_diagnostic(
    dialog: StartupErrorDialog,
) -> None:
    diagnostic = dialog.details.toPlainText()
    failed_reply = FakeReply(b"invalid metadata")
    dialog.updates.client.manager.get.return_value = failed_reply
    dialog.update_panel.check_updates.click()
    assert not dialog.update_panel.check_updates.isEnabled()
    assert not dialog.update_panel.update_channel.isEnabled()

    failed_reply.finished.emit()

    assert "Échec de la mise à jour" in dialog.update_panel.update_status.text()
    assert dialog.update_panel.check_updates.isEnabled()
    assert dialog.update_panel.update_channel.isEnabled()
    successful_reply = FakeReply()
    dialog.updates.client.manager.get.return_value = successful_reply
    dialog.update_panel.check_updates.click()
    successful_reply.finished.emit()
    assert dialog.update_panel.update_status.text() == "Aucune mise à jour disponible."
    assert dialog.details.toPlainText() == diagnostic
    assert dialog.isVisible()


def test_recovery_should_not_download_or_close_when_installation_is_declined(
    dialog: StartupErrorDialog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_controller, "can_install", lambda: True)
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.No)
    download = Mock()
    monkeypatch.setattr(dialog.updates.client, "download", download)
    dialog.updates.client.checked.emit(available())

    dialog.update_panel.install_update.click()

    download.assert_not_called()
    assert not dialog.updates._install_confirmed
    assert dialog.isVisible()


@pytest.mark.parametrize("valid_download", [True, False])
def test_recovery_should_launch_installer_only_after_confirmation_and_digest_verification(
    dialog: StartupErrorDialog,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid_download: bool,
) -> None:
    payload = b"verified installer"
    body = payload
    if not valid_download:
        body = b"x" * len(payload)
    reply = FakeReply(body)
    dialog.updates.client.manager.get.return_value = reply
    monkeypatch.setattr(update_controller, "can_install", lambda: True)
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QStandardPaths, "writableLocation", lambda _: str(tmp_path))
    launch = Mock(return_value=(True, 123))
    monkeypatch.setattr(update_controller.QProcess, "startDetached", launch)
    dialog.updates.client.checked.emit(available(payload=payload))
    assert dialog.update_panel.install_update.text() == "Télécharger et installer"
    dialog.update_panel.install_update.click()
    assert dialog.isVisible(), "An accepted confirmation must not close before download succeeds"
    dialog.updates.client.progress.emit(50)
    assert dialog.update_panel.update_status.text() == "Téléchargement : 50 %"
    launch.assert_not_called()

    reply.finished.emit()

    if valid_download:
        launch.assert_called_once()
        path, arguments = launch.call_args.args
        assert Path(path).read_bytes() == payload
        assert arguments == [f"/DIR={Path(update_controller.sys.executable).parent}"]
        assert not dialog.isVisible()
    else:
        launch.assert_not_called()
        assert dialog.isVisible()
        assert "Échec de la mise à jour" in dialog.update_panel.update_status.text()


def test_recovery_should_keep_window_open_when_starting_the_installer_fails(
    dialog: StartupErrorDialog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_controller, "can_install", lambda: True)
    launch = Mock(return_value=(False, 0))
    monkeypatch.setattr(update_controller.QProcess, "startDetached", launch)
    dialog.updates._install_confirmed = True

    dialog.updates.client.downloaded.emit("fake-installer.exe")

    assert dialog.isVisible()
    assert "Échec de la mise à jour" in dialog.update_panel.update_status.text()


def test_recovery_should_open_the_release_page_for_a_portable_build_after_confirmation(
    dialog: StartupErrorDialog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_controller, "can_install", lambda: False)
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    browser = Mock(return_value=True)
    monkeypatch.setattr(update_controller.QDesktopServices, "openUrl", browser)
    release = available()
    dialog.updates.client.checked.emit(release)

    dialog.update_panel.install_update.click()

    assert browser.call_args.args[0].toString() == release.page_url
    dialog.updates.client.manager.get.assert_not_called()
    assert dialog.isVisible()


def test_recovery_should_abort_pending_requests_and_ignore_their_late_completion_on_close(
    dialog: StartupErrorDialog,
) -> None:
    reply = dialog.updates.client.manager.get.return_value
    dialog.update_panel.check_updates.click()

    dialog.close()
    reply.finished.emit()

    assert reply.aborted
    assert dialog.updates.client.reply is None
    assert dialog.updates.release is None
    assert not dialog.updates.client.timer.isActive()


def test_recovery_should_not_launch_a_download_completed_after_the_error_window_is_closed(
    dialog: StartupErrorDialog,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = FakeReply(b"verified installer")
    dialog.updates.client.manager.get.return_value = reply
    monkeypatch.setattr(update_controller, "can_install", lambda: True)
    monkeypatch.setattr(QMessageBox, "exec", lambda _: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QStandardPaths, "writableLocation", lambda _: str(tmp_path))
    launch = Mock()
    monkeypatch.setattr(update_controller.QProcess, "startDetached", launch)
    dialog.updates.client.checked.emit(available())
    dialog.update_panel.install_update.click()

    dialog.close()
    reply.finished.emit()

    assert reply.aborted
    launch.assert_not_called()


def test_recovery_should_offer_a_release_link_when_package_metadata_is_unreadable(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        update_controller, "version", Mock(side_effect=OSError("unreadable metadata"))
    )
    widget = StartupErrorDialog(StartupStage.RESOURCES, OSError("missing files"), None)
    try:
        assert "Version locale inconnue" in widget.update_panel.current_version.text()
        assert not widget.update_panel.check_updates.isEnabled()
        assert RELEASE_URL in widget.update_panel.release_link.text()
    finally:
        widget.close()


def test_recovery_should_translate_the_schema_message_and_update_controls(
    application: QApplication,
) -> None:
    manager = language_manager()
    manager.set_language("en")
    widget = StartupErrorDialog(StartupStage.DATABASE, NewerDatabaseSchemaError(7, 6), None)
    try:
        assert widget.message.text() == "This version of RocketLantern cannot open this data."
        assert "including previews" in widget.hint.text()
        assert widget.update_panel.title() == "Updates"
        assert widget.update_panel.update_channel.itemText(0) == "Stable updates"
        assert widget.update_panel.check_updates.text() == "Check now"
    finally:
        widget.close()
        manager.set_language("fr")
