"""Coordinate filtered counters, persisted placement and the optional Windows guard."""

import json
import logging
import sqlite3
import sys
from dataclasses import replace
from importlib.metadata import version

from PySide6.QtCore import QObject, QRect, QSignalBlocker, Signal
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QDialog, QWidget

from rocket_lantern.game_presence import GamePresence, GamePresenceMonitor
from rocket_lantern.i18n import text as T
from rocket_lantern.overlay_monitor import OverlayMonitor
from rocket_lantern.overlay_placement import (
    OverlayPlacement,
    parse_placement,
    placement_from_position,
)
from rocket_lantern.overlay_placement_dialog import OverlayPlacementDialog, PlacementDialog
from rocket_lantern.overlay_settings import OverlaySettings
from rocket_lantern.result_summary import ResultSummary
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.summary_overlay import SummaryOverlay
from rocket_lantern.windows_overlay import WindowsOverlayApi

LOGGER = logging.getLogger(__name__)


class DesktopOverlayController(QObject):
    """Share window lifecycle, placement and diagnostics between independent HUDs."""

    failed = Signal()

    def __init__(
        self,
        controls: OverlaySettings,
        owner: QWidget,
        store: MatchStore,
        placement_key: str,
        enabled_key: str,
        default_corner: str = "top_left",
        presence: GamePresenceMonitor | None = None,
    ) -> None:
        super().__init__(owner)
        self.controls = controls
        self.store = store
        self._placement_key = placement_key
        self._enabled_key = enabled_key
        self._enabled = store.setting(enabled_key) == "1"
        self.presence = presence
        if presence is not None:
            presence.changed.connect(self._presence_changed)
        self.window: QWidget | None = None
        self.editor: PlacementDialog | None = None
        self._closing = False
        self._activation_pending = False
        self.monitor: OverlayMonitor | None = None
        self._native_error = ""
        self._placement = OverlayPlacement(corner=default_corner)
        saved = store.setting(placement_key)
        if saved != "":
            try:
                self._placement = parse_placement(saved)
            except ValueError:
                LOGGER.warning("Ignoring an invalid saved overlay placement")
        self._connected_screens: set[QScreen] = set()
        controls.enabled.toggled.connect(self._enabled_changed)
        controls.monitor.currentIndexChanged.connect(self._screen_changed)
        controls.corner.currentIndexChanged.connect(self._corner_changed)
        controls.place_button.clicked.connect(self._edit_placement)
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._refresh_screens)
        app.screenRemoved.connect(self._refresh_screens)
        self._refresh_screens()
        self._sync_corner()

    def restore_activation(self) -> None:
        """Restore preferences once the owner and subclass are fully initialized."""
        if not self._can_restore_activation():
            self._enabled = False
        with QSignalBlocker(self.controls.enabled):
            self.controls.enabled.setChecked(self._enabled)
        self._toggle(self._enabled)

    def _can_restore_activation(self) -> bool:
        return True

    def _activation_settings(self, enabled: bool) -> dict[str, str]:
        value = "0"
        if enabled:
            value = "1"
        return {self._enabled_key: value}

    def _enabled_changed(self, enabled: bool) -> None:
        if self._closing or self._activation_pending:
            return
        self._toggle(enabled)
        if self._closing:
            return
        selected = self.controls.enabled.isChecked()
        if selected == self._enabled:
            return
        try:
            self.store.set_settings(self._activation_settings(selected))
        except sqlite3.Error:
            with QSignalBlocker(self.controls.enabled):
                self.controls.enabled.setChecked(self._enabled)
            self._toggle(self._enabled)
            self.failed.emit()
            return
        self._enabled = selected

    def _sync_corner(self) -> None:
        mode = self._placement.corner
        if self._placement.x_ratio is not None:
            mode = "custom"
        with QSignalBlocker(self.controls.corner):
            self.controls.corner.setCurrentIndex(self.controls.corner.findData(mode))

    def _set_placement(self, placement: OverlayPlacement) -> None:
        try:
            self.store.set_setting(self._placement_key, placement.serialize())
        except sqlite3.Error:
            self._sync_corner()
            self.failed.emit()
            return
        self._placement = placement
        self._sync_corner()
        self._reposition()

    def _screen_changed(self, index: int) -> None:
        if not self._closing:
            self._set_placement(
                replace(self._placement, screen=self.controls.monitor.currentData())
            )

    def _corner_changed(self, index: int) -> None:
        if self._closing:
            return
        corner = self.controls.corner.currentData()
        if corner == "custom":
            self._edit_placement()
            return
        self._set_placement(OverlayPlacement(self.controls.monitor.currentData(), corner))

    def _selected_screen(self) -> QScreen | None:
        name = self.controls.monitor.currentData()
        for screen in QGuiApplication.screens():
            if screen.name() == name:
                return screen
        return QGuiApplication.primaryScreen()

    def _edit_placement(self) -> None:
        if self._closing:
            return
        if self.editor is not None:
            self.editor.raise_()
            return
        screen = self._selected_screen()
        if screen is None:
            self._sync_corner()
            return
        if self.monitor is not None:
            self.monitor.stop()
        if self.window is not None:
            self.window.hide()
        bounds = screen.availableGeometry()
        self.editor = self._create_editor(bounds)
        point = self._placement.position(bounds, self.editor.preview.size())
        self.editor.preview.place(point - bounds.topLeft())
        self.editor.finished.connect(self._placement_finished)
        self.editor.open()

    def _placement_finished(self, result: int) -> None:
        editor = self.editor
        if editor is None:
            return
        self.editor = None
        screen = self._selected_screen()
        if not self._closing and result == QDialog.DialogCode.Accepted and screen is not None:
            self._set_placement(
                placement_from_position(
                    screen.name(),
                    self._placement.corner,
                    screen.availableGeometry(),
                    editor.preview.size(),
                    editor.selected_position(),
                )
            )
        editor.deleteLater()
        self._sync_corner()
        if not self._closing:
            self._toggle(self.controls.enabled.isChecked())

    def _start_monitor(self) -> None:
        if self.window is None:
            return
        if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
            return
        try:
            if self.monitor is None:
                self.monitor = OverlayMonitor(WindowsOverlayApi(), self, presence=self.presence)
            self.monitor.start(int(self.window.winId()))
        except OSError as error:
            self._native_error = str(error)
            LOGGER.warning("Windows overlay placement failed: %s", error)

    def diagnostic(self) -> str:
        """Preserve the in-game observation after Alt+Tab, without player identities."""
        rectangle = None
        if self.window is not None:
            geometry = self.window.geometry()
            rectangle = (geometry.x(), geometry.y(), geometry.width(), geometry.height())
        result: dict[str, object] = {
            "version": version("rocket-lantern"),
            "platform": sys.platform,
            "qt_platform": QGuiApplication.platformName(),
            "enabled": self.controls.enabled.isChecked(),
            "selected_screen": self.controls.monitor.currentData(),
            "placement": json.loads(self._placement.serialize()),
            "overlay_qt_rect_xywh": rectangle,
            "native_monitor_running": self.monitor is not None and self.monitor.window != 0,
            "native_initialization_error": self._native_error,
            "last_game_observation": None,
            "note": "Z-order does not prove rendered visibility or exclusive-fullscreen mode.",
        }
        if self.monitor is not None:
            result["last_game_observation"] = self.monitor.observation.diagnostic()
        return json.dumps(result, indent=2, ensure_ascii=False)

    def _refresh_screens(self, changed: object = None) -> None:
        if self._closing:
            return
        if self.editor is not None:
            self.editor.reject()
        selected = self._placement.screen or self.controls.monitor.currentData()
        screens = QGuiApplication.screens()
        self._connected_screens.intersection_update(screens)
        primary = QGuiApplication.primaryScreen()
        with QSignalBlocker(self.controls.monitor):
            self.controls.monitor.clear()
            for screen in screens:
                label = screen.name()
                if screen is primary:
                    label = T("{name} (principal)", name=label)
                self.controls.monitor.addItem(label, screen.name())
                if screen not in self._connected_screens:
                    screen.availableGeometryChanged.connect(self._refresh_screens)
                    self._connected_screens.add(screen)
            index = self.controls.monitor.findData(selected)
            if index < 0 and primary is not None:
                index = self.controls.monitor.findData(primary.name())
            self.controls.monitor.setCurrentIndex(max(0, index))
        available = len(screens) > 0
        self.controls.enabled.setEnabled(available)
        self.controls.place_button.setEnabled(available)
        self._reposition()
        self._toggle(self.controls.enabled.isChecked())

    def _toggle(self, enabled: bool) -> None:
        if self._closing or self._activation_pending:
            return
        if enabled:
            # A modal warning runs a nested event loop: telemetry can arrive during consent.
            self._activation_pending = True
            try:
                allowed = self._allow_activation()
            finally:
                self._activation_pending = False
            if self._closing:
                return
            if not allowed:
                with QSignalBlocker(self.controls.enabled):
                    self.controls.enabled.setChecked(False)
            enabled = allowed and self.controls.enabled.isChecked()
        if (
            not enabled
            or self.editor is not None
            or (self.presence is not None and not self.presence.allows_overlay)
            or self._selected_screen() is None
            or not self._has_content()
        ):
            if self.monitor is not None:
                self.monitor.stop()
            if self.window is not None:
                self.window.hide()
            return
        if self.window is None:
            self.window = self._create_window()
        self._refresh_window()
        self._reposition()
        if not self.window.isVisible():
            self.window.show()
            self._start_monitor()

    def _presence_changed(self, state: GamePresence) -> None:
        self._toggle(self.controls.enabled.isChecked())

    def _allow_activation(self) -> bool:
        return True

    def _has_content(self) -> bool:
        return True

    def _create_window(self) -> QWidget:
        raise NotImplementedError

    def _create_editor(self, bounds: QRect) -> PlacementDialog:
        raise NotImplementedError

    def _refresh_window(self) -> None:
        raise NotImplementedError

    def _reposition(self) -> None:
        if self._closing or self.window is None:
            return
        screen = self._selected_screen()
        if screen is not None:
            self.window.move(
                self._placement.position(screen.availableGeometry(), self.window.size())
            )

    def shutdown(self) -> None:
        """Close both top-level windows and prevent late callbacks from showing either."""
        self._closing = True
        if self.editor is not None:
            self.editor.reject()
        if self.monitor is not None:
            self.monitor.stop()
        if self.window is not None:
            self.window.close()
            self.window.deleteLater()
            self.window = None


class OverlayController(DesktopOverlayController):
    """Keep the W/L HUD synchronized with the application's filtered counters."""

    def __init__(
        self,
        controls: OverlaySettings,
        counters: ResultSummary,
        owner: QWidget,
        store: MatchStore,
        presence: GamePresenceMonitor | None = None,
    ) -> None:
        self.counters = counters
        super().__init__(
            controls, owner, store, "overlay_placement", "overlay_enabled", presence=presence
        )
        counters.summary_changed.connect(self._update)

    def _create_window(self) -> SummaryOverlay:
        return SummaryOverlay()

    def _create_editor(self, bounds: QRect) -> OverlayPlacementDialog:
        return OverlayPlacementDialog(
            bounds,
            bounds.topLeft(),
            self.counters.summary,
            self._placement.corner,
            self.controls.window(),
        )

    def _refresh_window(self) -> None:
        if isinstance(self.window, SummaryOverlay):
            self.window.set_summary(self.counters.summary)

    def _update(self, summary: Summary) -> None:
        if self._closing:
            return
        if self.editor is not None:
            self.editor.preview.set_summary(summary)
            self.editor.preview.place(self.editor.preview.pos())
        self._refresh_window()
        self._reposition()
