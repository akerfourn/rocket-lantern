"""Coordinate optional setup, persisted discovery paths and shared preferences."""

import logging
import sqlite3

from PySide6.QtCore import QObject, QSignalBlocker, Signal
from PySide6.QtWidgets import QWidget

from rocket_lantern.game_installations_panel import ConfigurationCheck, GameInstallationsPanel
from rocket_lantern.i18n import language_manager
from rocket_lantern.installation_preferences import (
    ONBOARDING_KEY,
    load_installations,
    needs_onboarding,
    remember_discovery,
)
from rocket_lantern.onboarding_dialog import OnboardingDialog
from rocket_lantern.settings_panel import SettingsPanel
from rocket_lantern.storage import MatchStore

LOGGER = logging.getLogger(__name__)


class OnboardingController(QObject):
    """Never infer current game configuration from remembered discovery results."""

    failed = Signal()
    reconnect_requested = Signal()

    def __init__(self, store: MatchStore, settings: SettingsPanel, owner: QWidget) -> None:
        super().__init__(owner)
        self.store = store
        self.settings = settings
        self.owner = owner
        self.dialog: OnboardingDialog | None = None
        self._closing = False
        self._opening_port = settings.port.value()
        self._automatic_pending = needs_onboarding(store)
        self._known = load_installations(store)
        panel = settings.game_installations
        panel.restore_installations(self._known)
        panel.configurations_checked.connect(self._settings_checked)
        panel.configuration_updated.connect(self._settings_updated)
        panel.packet_rate.valueChanged.connect(self._sync_rate)
        panel.busy_changed.connect(self._settings_busy)
        settings.onboarding_button.clicked.connect(self.open)
        settings.port.valueChanged.connect(self._sync_port)
        language_manager().changed.connect(self._sync_language)

    def offer(self) -> None:
        """Offer setup once after normal application startup, not on reconnection."""
        if self._automatic_pending:
            self._automatic_pending = False
            self.open()

    def open(self) -> None:
        """Allow manually reopening setup even after it was finished or skipped."""
        if self._closing:
            return
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        panel = self.settings.game_installations
        if panel.is_busy:
            return
        self._opening_port = self.settings.port.value()
        self.dialog = OnboardingDialog(
            self.settings.port.value(),
            self.settings.language.currentData(),
            panel.packet_rate.value(),
            self.owner,
        )
        dialog = self.dialog
        dialog.installations.restore_installations(self._known)
        dialog.installations.configurations_checked.connect(self._onboarding_checked)
        dialog.installations.configuration_updated.connect(self._onboarding_updated)
        dialog.installations.packet_rate.valueChanged.connect(panel.packet_rate.setValue)
        dialog.port.valueChanged.connect(self.settings.port.setValue)
        dialog.language.currentIndexChanged.connect(self._change_language)
        dialog.finished.connect(self._finished)
        dialog.open()

    def shutdown(self) -> None:
        """Ignore late worker results before the application closes its database."""
        self._closing = True
        if self.dialog is not None:
            self.dialog.hide()

    def _finished(self, result: int) -> None:
        dialog = self.dialog
        if dialog is None:
            return
        self.dialog = None
        self._automatic_pending = False
        if self._closing:
            return
        try:
            self.store.set_setting(ONBOARDING_KEY, dialog.outcome)
        except sqlite3.Error:
            LOGGER.exception("Cannot save onboarding status")
            self.failed.emit()
        if dialog.outcome == "completed" and self.settings.port.value() != self._opening_port:
            self.reconnect_requested.emit()

    def _settings_busy(self, busy: bool) -> None:
        self.settings.onboarding_button.setEnabled(not busy)

    def _sync_rate(self, rate: int) -> None:
        if self.dialog is not None:
            self.dialog.installations.set_packet_rate(rate)

    def _sync_port(self, port: int) -> None:
        if self.dialog is not None:
            self.dialog.port.setValue(port)

    def _sync_language(self, language: str) -> None:
        if self.dialog is not None:
            with QSignalBlocker(self.dialog.language):
                self.dialog.language.setCurrentIndex(self.dialog.language.findData(language))

    def _change_language(self, index: int) -> None:
        if self.dialog is not None:
            language = self.dialog.language.itemData(index)
            self.settings.language.setCurrentIndex(self.settings.language.findData(language))

    def _remember(self, check: ConfigurationCheck, source: GameInstallationsPanel) -> None:
        if self._closing:
            return
        try:
            self._known = remember_discovery(self.store, check.discovery)
        except sqlite3.Error:
            LOGGER.exception("Cannot save discovered installations")
            self.failed.emit()
            return
        self._invalidate_other_panel(source)

    def _invalidate_other_panel(self, source: GameInstallationsPanel) -> None:
        settings_panel = self.settings.game_installations
        if source is not settings_panel:
            settings_panel.restore_installations(self._known)
        elif self.dialog is not None:
            self.dialog.installations.restore_installations(self._known)

    def _settings_checked(self, check: ConfigurationCheck) -> None:
        self._remember(check, self.settings.game_installations)

    def _onboarding_checked(self, check: ConfigurationCheck) -> None:
        if self.dialog is not None:
            self._remember(check, self.dialog.installations)

    def _settings_updated(self) -> None:
        self._invalidate_other_panel(self.settings.game_installations)

    def _onboarding_updated(self) -> None:
        if self.dialog is not None:
            self._invalidate_other_panel(self.dialog.installations)
