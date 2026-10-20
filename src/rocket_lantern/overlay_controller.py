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
from rocket_lantern.summary_overlay_content import SummaryOverlayContent, parse_summary_content
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
        *,
        opacity_key: str = "overlay_opacity",
    ) -> None:
        super().__init__(owner)
        self.controls = controls
        self.store = store
        self._placement_key = placement_key
        self._enabled_key = enabled_key
        self._opacity_key = opacity_key
        self._opacity = self._load_opacity()
        controls.set_opacity(self._opacity)
        self._activation = self._load_activation()
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
        controls.activation_changed.connect(self._activation_changed)
        controls.opacity_changed.connect(self._opacity_changed)
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
            self._activation = self.controls.inactive_value
        self.controls.set_activation_value(self._activation)
        self._toggle(self.controls.activation_enabled())

    def _can_restore_activation(self) -> bool:
        return True

    def _load_activation(self) -> str:
        saved = self.store.setting(self._enabled_key)
        if saved in self.controls.activation_values:
            return saved
        return self.controls.inactive_value

    def _load_opacity(self) -> int:
        saved = self.store.setting(self._opacity_key)
        if saved == "":
            return 100
        try:
            opacity = int(saved)
            if self.controls.opacity.minimum() <= opacity <= self.controls.opacity.maximum():
                return opacity
        except ValueError:
            pass
        LOGGER.warning("Ignoring invalid saved overlay opacity: %s", self._opacity_key)
        return 100

    def _opacity_changed(self, value: int) -> None:
        if self._closing or value == self._opacity:
            return
        try:
            self.store.set_setting(self._opacity_key, str(value))
        except sqlite3.Error:
            self.controls.set_opacity(self._opacity)
            self.failed.emit()
            return
        self._opacity = value
        if self.window is not None:
            self.window.setWindowOpacity(value / 100)
        if self.editor is not None:
            self.editor.preview.set_opacity(value)

    def _activation_settings(self, value: str) -> dict[str, str]:
        return {self._enabled_key: value}

    def _activation_changed(self, value: str) -> None:
        if self._closing or self._activation_pending:
            return
        self._toggle(self.controls.activation_enabled())
        if self._closing:
            return
        selected = self.controls.activation_value()
        if selected == self._activation:
            return
        try:
            self.store.set_settings(self._activation_settings(selected))
        except sqlite3.Error:
            self.controls.set_activation_value(self._activation)
            self._toggle(self.controls.activation_enabled())
            self.failed.emit()
            return
        self._activation = selected

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
        if self._closing or not self._can_place():
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
        self.editor.preview.set_opacity(self._opacity)
        point = self._placement.position(bounds, self.editor.preview.size())
        self.editor.preview.place(point - bounds.topLeft())
        self.editor.set_horizontal_anchor(self._placement.editor_anchor())
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
                    editor.anchor_buttons.selected_anchor(),
                )
            )
        editor.deleteLater()
        self._sync_corner()
        if not self._closing:
            self._toggle(self.controls.activation_enabled())

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
            "enabled": self.controls.activation_enabled(),
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
        self.controls.activation_control.setEnabled(available)
        self.controls.place_button.setEnabled(available and self._can_place())
        self._reposition()
        self._toggle(self.controls.activation_enabled())

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
                self.controls.set_activation_value(self.controls.inactive_value)
            enabled = allowed and self.controls.activation_enabled()
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
            self.window.setWindowOpacity(self._opacity / 100)
        self._refresh_window()
        self._reposition()
        if not self.window.isVisible():
            self.window.show()
            self._start_monitor()

    def _presence_changed(self, state: GamePresence) -> None:
        self._toggle(self.controls.activation_enabled())

    def _allow_activation(self) -> bool:
        return True

    def _has_content(self) -> bool:
        return True

    def _can_place(self) -> bool:
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
        self.catalog = counters.evaluations.catalog
        self._content = SummaryOverlayContent()
        saved = store.setting("summary_overlay_content")
        if saved != "":
            try:
                self._content = parse_summary_content(saved)
            except ValueError:
                LOGGER.warning("Ignoring invalid saved summary overlay content")
        controls.content.set_content(self._content)
        super().__init__(
            controls, owner, store, "overlay_placement", "overlay_enabled", presence=presence
        )
        counters.summary_changed.connect(self._update)
        controls.content.changed.connect(self._content_changed)
        counters.evaluations.changed.connect(self._refresh_content)
        self.catalog.changed.connect(self._refresh_content)

    def _content_changed(self) -> None:
        if self._closing:
            return
        content = self.controls.content.content
        if content == self._content:
            return
        try:
            self.store.set_setting("summary_overlay_content", content.serialize())
        except sqlite3.Error:
            self.controls.content.set_content(self._content)
            self.failed.emit()
            return
        self._content = content
        self._refresh_content()

    def _has_content(self) -> bool:
        return self._content.has_content(self.catalog)

    def _can_place(self) -> bool:
        return self._has_content()

    def _refresh_content(self) -> None:
        if self._closing:
            return
        self.controls.place_button.setEnabled(
            self._selected_screen() is not None and self._can_place()
        )
        if self.editor is not None:
            self.editor.preview.set_content(
                self._content, self.catalog, self.counters.evaluations.choices
            )
        self._refresh_window()
        self._reposition()
        self._toggle(self.controls.activation_enabled())

    def _create_window(self) -> SummaryOverlay:
        return SummaryOverlay()

    def _create_editor(self, bounds: QRect) -> OverlayPlacementDialog:
        editor = OverlayPlacementDialog(
            bounds,
            bounds.topLeft(),
            self.counters.summary,
            self._placement.corner,
            self.controls.window(),
        )
        editor.preview.set_content(self._content, self.catalog, self.counters.evaluations.choices)
        return editor

    def _refresh_window(self) -> None:
        if isinstance(self.window, SummaryOverlay):
            self.window.set_summary(self.counters.summary)
            self.window.set_content(self._content, self.catalog, self.counters.evaluations.choices)

    def _update(self, summary: Summary) -> None:
        if self._closing:
            return
        if self.editor is not None:
            self.editor.preview.set_summary(summary)
            self.editor.preview.place(self.editor.preview.pos())
        self._refresh_window()
        self._reposition()
