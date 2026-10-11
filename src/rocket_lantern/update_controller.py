"""Connect update preferences, notifications and explicit install confirmation."""

import sqlite3
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMainWindow, QMessageBox

from rocket_lantern.i18n import text as T
from rocket_lantern.settings_panel import SettingsPanel
from rocket_lantern.storage import MatchStore
from rocket_lantern.translated_widgets import TranslatedButton, set_text
from rocket_lantern.update_client import UpdateClient
from rocket_lantern.updates import CHANNELS, UpdateRelease, version_key


def download_icon(unstable: bool) -> QIcon:
    """Use a colored download arrow rather than font-dependent symbols."""
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    color = "#23834a"
    if unstable:
        color = "#c87518"
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(color), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(12, 3, 12, 15)
        painter.drawLine(7, 10, 12, 15)
        painter.drawLine(17, 10, 12, 15)
        painter.drawLine(4, 17, 4, 21)
        painter.drawLine(4, 21, 20, 21)
        painter.drawLine(20, 21, 20, 17)
    finally:
        painter.end()
    return QIcon(pixmap)


def can_install() -> bool:
    """Only an installed Windows bundle may replace itself through Inno Setup."""
    return (
        sys.platform == "win32"
        and getattr(sys, "frozen", False)
        and (Path(sys.executable).parent / "unins000.exe").is_file()
    )


class UpdateController(QObject):
    """No network runs until start() is called by the real application entry point."""

    def __init__(self, window: QMainWindow, settings: SettingsPanel, store: MatchStore) -> None:
        super().__init__(window)
        self.window = window
        self.settings = settings
        self.store = store
        self.release: UpdateRelease | None = None
        self._install_confirmed = False
        self._active = False
        self._busy = False
        try:
            self.current = version("rocket-lantern")
        except PackageNotFoundError:
            self.current = ""
        channel = store.setting("update_channel")
        if channel not in CHANNELS:
            channel = "stable"
        settings.update_channel.setCurrentIndex(settings.update_channel.findData(channel))
        self.client = UpdateClient(self.current, channel, self)
        self.button = TranslatedButton()
        self.button.setFixedSize(30, 30)
        self.button.hide()
        self.button.clicked.connect(self.show_confirmation)
        settings.update_channel.currentIndexChanged.connect(self._change_channel)
        settings.check_updates.clicked.connect(self.client.check)
        settings.install_update.clicked.connect(self.show_confirmation)
        self.client.checked.connect(self._checked)
        self.client.failed.connect(self._failed)
        self.client.busy_changed.connect(self._set_busy)
        self.client.downloaded.connect(self._install)
        self.client.progress.connect(self._progress)
        self._show_channel(channel)

    def start(self) -> None:
        self._active = True
        if version_key(self.current) is None:
            self.settings.update_status.setText(
                T("Version locale inconnue ; vérification impossible.")
            )
            return
        self.client.start()

    def _show_channel(self, channel: str) -> None:
        self.settings.update_warning.setVisible(channel == "all")
        self.settings.check_updates.setEnabled(
            channel != "disabled" and not self._busy and version_key(self.current) is not None
        )
        if channel == "disabled":
            self.settings.update_status.setText(T("Détection des mises à jour désactivée."))
        else:
            self.settings.update_status.setText(
                T("Version actuelle : {version}", version=self.current)
            )

    def _change_channel(self, index: int) -> None:
        channel = self.settings.update_channel.itemData(index)
        try:
            self.store.set_setting("update_channel", channel)
        except sqlite3.Error:
            with QSignalBlocker(self.settings.update_channel):
                self.settings.update_channel.setCurrentIndex(
                    self.settings.update_channel.findData(self.client.channel)
                )
            self.settings.update_status.setText(T("Impossible d’enregistrer les paramètres."))
            return
        self.release = None
        self.button.hide()
        self.settings.install_update.hide()
        self._show_channel(channel)
        if self._active:
            self.client.set_channel(channel)
        else:
            self.client.channel = channel

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.settings.check_updates.setEnabled(
            not busy and self.client.channel != "disabled" and version_key(self.current) is not None
        )
        self.settings.install_update.setEnabled(not busy)
        self.settings.update_channel.setEnabled(not busy)
        self.button.setEnabled(not busy)
        if busy:
            self.settings.update_status.setText(T("Vérification ou téléchargement en cours…"))

    def _checked(self, release: UpdateRelease | None) -> None:
        self.release = release
        self.button.setVisible(release is not None)
        self.settings.install_update.setVisible(release is not None)
        if release is None:
            self.settings.update_status.setText(T("Aucune mise à jour disponible."))
            return
        notice = T("Mise à jour disponible : {version}", version=release.version)
        if release.unstable:
            notice = T("Préversion disponible : {version}", version=release.version)
        self.settings.update_status.setText(notice)
        self.button.setIcon(download_icon(release.unstable))
        self.button.setToolTip(notice)
        # Use the same translated source for assistive technology.
        set_text(self.button, "accessibleName", notice, self.button.setAccessibleName)
        label = T("Télécharger et installer")
        if not can_install() or release.download_url == "":
            label = T("Ouvrir la page de téléchargement")
        self.settings.install_update.setText(label)

    def show_confirmation(self) -> None:
        release = self.release
        if release is None or self._busy:
            return
        install = can_install() and release.download_url != ""
        message = T(
            "Télécharger et installer la version {version} ? RocketLantern sera fermé "
            "et l’installateur Windows s’ouvrira. Vos données seront conservées.",
            version=release.version,
        )
        if not install:
            message = T(
                "Ouvrir la release {version} dans le navigateur ? Pour une version portable "
                "ou lancée depuis les sources, la mise à jour se fait manuellement.",
                version=release.version,
            )
        question = QMessageBox(self.window)
        question.setWindowTitle(str(T("Mise à jour")))
        question.setText(str(message))
        if release.unstable:
            question.setInformativeText(
                str(T("Les versions en développement peuvent comporter des bugs."))
            )
        question.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        question.button(QMessageBox.StandardButton.Yes).setText(str(T("Oui")))
        question.button(QMessageBox.StandardButton.No).setText(str(T("Non")))
        question.setDefaultButton(QMessageBox.StandardButton.No)
        if question.exec() != QMessageBox.StandardButton.Yes:
            return
        if install:
            self._install_confirmed = True
            self.client.download(release)
        elif not QDesktopServices.openUrl(QUrl(release.page_url)):
            self._failed()

    def _progress(self, percent: int) -> None:
        self.settings.update_status.setText(T("Téléchargement : {percent} %", percent=percent))

    def _failed(self) -> None:
        self._install_confirmed = False
        self.settings.update_status.setText(
            T("Échec de la mise à jour. Vérifiez la connexion et réessayez.")
        )

    def _install(self, path: str) -> None:
        if not self._install_confirmed or not can_install():
            return
        self._install_confirmed = False
        started, _ = QProcess.startDetached(path, [f"/DIR={Path(sys.executable).parent}"])
        if not started:
            self._failed()
            return
        self.window.close()
