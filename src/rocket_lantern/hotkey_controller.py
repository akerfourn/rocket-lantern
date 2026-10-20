"""Persist optional shortcuts and suspend them while their settings are edited."""

import logging
import sqlite3

from PySide6.QtCore import QObject, QSignalBlocker, Signal

from rocket_lantern.global_hotkeys import (
    GlobalHotkeys,
    HotkeyError,
    HotkeyProblem,
    validate_hotkeys,
)
from rocket_lantern.i18n import Text
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.settings_panel import SettingsPanel
from rocket_lantern.storage import MatchStore

LOGGER = logging.getLogger(__name__)


def problem_text(problem: HotkeyProblem) -> Text:
    match problem:
        case HotkeyProblem.UNSUPPORTED:
            return T("Les raccourcis globaux sont disponibles sous Windows uniquement.")
        case HotkeyProblem.DUPLICATE:
            return T("Chaque évaluation doit avoir un raccourci différent.")
        case HotkeyProblem.INVALID:
            return T("Utilise Ctrl, Alt ou Maj avec une lettre, un chiffre ou F1–F24 (sauf F12).")
        case HotkeyProblem.CONFLICT:
            return T("Raccourci indisponible ou déjà utilisé. Aucun raccourci n’est actif.")
    raise ValueError("Unknown hotkey problem")


class HotkeyController(QObject):
    failed = Signal()
    registration_failed = Signal()
    activated = Signal(str)

    def __init__(
        self, settings: SettingsPanel, store: MatchStore, manager: GlobalHotkeys | None = None
    ) -> None:
        super().__init__(settings)
        self.settings = settings
        self.panel = settings.hotkeys
        self.store = store
        self.catalog = settings.catalog
        if self.catalog.repository is None:
            self.catalog = LabelCatalog(store.labels, self)
        self.manager = manager
        if self.manager is None:
            self.manager = GlobalHotkeys(self)
        self._shutdown = False
        self.problem: HotkeyProblem | None = None
        self._enabled = store.setting("evaluation_hotkeys_enabled") in ("", "1")
        self._bindings = self.catalog.bindings()
        try:
            validate_hotkeys(tuple(self._bindings.values()), expected_count=None)
        except ValueError:
            LOGGER.warning("Invalid saved label shortcuts; keeping them disabled")
            self._enabled = False
        with QSignalBlocker(self.panel.enabled):
            self.panel.enabled.setChecked(self._enabled)
        self.manager.activated.connect(self.activated)
        self.panel.enabled.toggled.connect(self.set_enabled)
        settings.opened.connect(self.suspend)
        settings.hidden.connect(self.resume)
        settings.labels.opened.connect(self.suspend)
        settings.labels.hidden.connect(self.resume)
        self.catalog.changed.connect(self.reload)
        self.resume()

    def reload(self) -> None:
        self._bindings = self.catalog.bindings()
        self.resume()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            try:
                validate_hotkeys(tuple(self._bindings.values()), expected_count=None)
            except HotkeyError as error:
                self.panel.status.setText(problem_text(error.problem))
                self._restore_enabled()
                return
        try:
            self.store.set_setting("evaluation_hotkeys_enabled", str(int(enabled)))
        except sqlite3.Error:
            self._restore_enabled()
            self.panel.status.setText(T("Impossible d’enregistrer les raccourcis."))
            self.failed.emit()
            return
        self._enabled = enabled
        self.problem = None
        self.resume()
        self.settings.resize_to_contents()

    def _restore_enabled(self) -> None:
        with QSignalBlocker(self.panel.enabled):
            self.panel.enabled.setChecked(self._enabled)

    def suspend(self) -> None:
        self.manager.stop()
        if self._enabled and self.problem is None:
            self.panel.status.setText(
                T("Raccourcis suspendus dans les paramètres ; actifs après fermeture.")
            )

    def resume(self) -> None:
        if self._shutdown:
            return
        self.manager.stop()
        if not self._enabled:
            self.problem = None
            self.panel.status.setText(
                T("Raccourcis désactivés · l’évaluation à la souris reste disponible.")
            )
            return
        if self.settings.isVisible() or self.settings.labels.isVisible():
            self.suspend()
            return
        try:
            self.manager.start_bindings(self._bindings)
        except HotkeyError as error:
            self.problem = error.problem
            self.panel.status.setText(problem_text(error.problem))
            self.registration_failed.emit()
            return
        except OSError:
            LOGGER.exception("Cannot register Windows assessment shortcuts")
            self.manager.stop()
            self.problem = HotkeyProblem.CONFLICT
            self.panel.status.setText(problem_text(HotkeyProblem.CONFLICT))
            self.registration_failed.emit()
            return
        self.problem = None
        self.panel.status.setText(
            T("Raccourcis actifs · ils modifient le match en cours ou le dernier match.")
        )

    def shutdown(self) -> None:
        self._shutdown = True
        self.manager.stop()
