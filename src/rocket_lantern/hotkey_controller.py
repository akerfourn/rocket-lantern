"""Persist optional shortcuts and suspend them while their settings are edited."""

import json
import logging
import sqlite3

from PySide6.QtCore import QObject, QSignalBlocker, Signal
from PySide6.QtGui import QKeySequence

from rocket_lantern.global_hotkeys import (
    DEFAULT_HOTKEYS,
    GlobalHotkeys,
    HotkeyError,
    HotkeyProblem,
    validate_hotkeys,
)
from rocket_lantern.i18n import Text
from rocket_lantern.i18n import text as T
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
        self.manager = manager
        if self.manager is None:
            self.manager = GlobalHotkeys(self)
        self._shutdown = False
        self.problem: HotkeyProblem | None = None
        self._enabled = store.setting("evaluation_hotkeys_enabled") == "1"
        self._sequences = self._load_sequences()
        for editor, value in zip(self.panel.editors, self._sequences, strict=True):
            editor.setKeySequence(QKeySequence(value))
        with QSignalBlocker(self.panel.enabled):
            self.panel.enabled.setChecked(self._enabled)
        self.panel.fields.setVisible(self._enabled)
        self.manager.activated.connect(self.activated)
        self.panel.apply_requested.connect(self.apply)
        settings.opened.connect(self.suspend)
        settings.hidden.connect(self.resume)
        self.resume()

    def _load_sequences(self) -> tuple[str, ...]:
        raw = self.store.setting("evaluation_hotkeys")
        if raw == "":
            return DEFAULT_HOTKEYS
        try:
            values = json.loads(raw)
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise ValueError("Invalid shortcut settings")
            sequences = tuple(values)
            validate_hotkeys(sequences)
        except (ValueError, TypeError):
            LOGGER.warning("Invalid saved assessment shortcuts; keeping them disabled")
            self._enabled = False
            return DEFAULT_HOTKEYS
        return sequences

    def apply(self) -> None:
        enabled = self.panel.enabled.isChecked()
        values = self.panel.sequences()
        if enabled:
            try:
                validate_hotkeys(values)
            except HotkeyError as error:
                self.panel.status.setText(problem_text(error.problem))
                return
        else:
            values = self._sequences
        try:
            self.store.set_settings(
                {
                    "evaluation_hotkeys_enabled": str(int(enabled)),
                    "evaluation_hotkeys": json.dumps(values),
                }
            )
        except sqlite3.Error:
            self.panel.status.setText(T("Impossible d’enregistrer les raccourcis."))
            self.failed.emit()
            return
        self._enabled = enabled
        self._sequences = values
        self.problem = None
        self.resume()
        self.settings.resize_to_contents()

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
        if self.settings.isVisible():
            self.suspend()
            return
        try:
            self.manager.start(self._sequences)
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
