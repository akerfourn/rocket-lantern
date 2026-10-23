"""Coordinate optional live scoreboard visibility, filtering and independent placement."""

import logging
import sqlite3

from PySide6.QtCore import QRect, QTimer
from PySide6.QtWidgets import QWidget

from rocket_lantern.game_presence import GamePresenceMonitor
from rocket_lantern.i18n import text as T
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.overlay_controller import DesktopOverlayController
from rocket_lantern.overlay_placement_dialog import DraggablePreview, PlacementDialog
from rocket_lantern.scoreboard_overlay import ScoreboardDisplay, ScoreboardOverlay
from rocket_lantern.scoreboard_overlay_scope import ScoreboardScope, scoreboard_players
from rocket_lantern.scoreboard_overlay_settings import ScoreboardOverlaySettings
from rocket_lantern.storage import MatchStore

LOGGER = logging.getLogger(__name__)


class ScoreboardOverlayController(DesktopOverlayController):
    def __init__(
        self,
        controls: ScoreboardOverlaySettings,
        live: LiveMatchPanel,
        owner: QWidget,
        store: MatchStore,
        presence: GamePresenceMonitor | None = None,
    ) -> None:
        self.live = live
        self.scoreboard_controls = controls
        self._scope = ScoreboardScope.ALL
        saved_scope = store.setting("scoreboard_overlay_scope")
        if saved_scope:
            try:
                self._scope = ScoreboardScope(saved_scope)
            except ValueError:
                LOGGER.warning("Ignoring an invalid saved scoreboard overlay scope")
        controls.set_players_scope(self._scope)
        self._snapshot: MatchSnapshot | None = None
        self._fresh = False
        super().__init__(
            controls,
            owner,
            store,
            "scoreboard_overlay_placement",
            "scoreboard_overlay_enabled",
            "bottom_left",
            presence,
            opacity_key="scoreboard_overlay_opacity",
        )
        self._expiry = QTimer(self)
        self._expiry.setSingleShot(True)
        self._expiry.setInterval(3000)
        self._expiry.timeout.connect(self._expire)
        controls.players_changed.connect(self._scope_changed)
        live.state_changed.connect(self._update)

    def _scope_changed(self, value: str) -> None:
        if self._closing:
            return
        scope = ScoreboardScope(value)
        if scope == self._scope:
            return
        try:
            self.store.set_setting("scoreboard_overlay_scope", scope.value)
        except sqlite3.Error:
            self.scoreboard_controls.set_players_scope(self._scope)
            self.failed.emit()
            return
        self._scope = scope
        if self.editor is not None:
            self._set_preview_content(self.editor.preview.display)
            self.editor.preview.fit_content()
        self._update()

    def _has_content(self) -> bool:
        snapshot = self.live.state.snapshot
        return (
            self._fresh
            and snapshot is not None
            and bool(
                scoreboard_players(
                    tuple(snapshot.players.values()), self.live.player_id, self._scope
                )
            )
        )

    def _create_window(self) -> ScoreboardOverlay:
        window = ScoreboardOverlay()
        window.size_changed.connect(self._reposition)
        return window

    def _refresh_window(self) -> None:
        if not isinstance(self.window, ScoreboardOverlay):
            return
        snapshot = self.live.state.snapshot
        players = ()
        if snapshot is not None:
            players = tuple(snapshot.players.values())
        self.window.set_players(
            players,
            self.live.player_id,
            self._scope,
            self.live.state.epic_saves,
            self.live.state.opponent_post_hits,
        )

    def _set_preview_content(self, display: ScoreboardDisplay) -> None:
        players = (
            PlayerStats(
                "preview-me",
                str(T("Mon joueur")),
                0,
                score=340,
                goals=2,
                assists=1,
                saves=3,
                shots=5,
            ),
            PlayerStats(
                "preview-mate",
                str(T("Coéquipier 1")),
                0,
                score=220,
                goals=1,
                assists=2,
                saves=1,
                shots=3,
            ),
            PlayerStats(
                "preview-opponent",
                str(T("Adversaire 1")),
                1,
                score=280,
                goals=2,
                assists=0,
                saves=2,
                shots=4,
            ),
            PlayerStats(
                "preview-opponent-2",
                str(T("Adversaire 2")),
                1,
                score=140,
                goals=0,
                assists=1,
                saves=1,
                shots=2,
            ),
        )
        display.set_players(
            players, "preview-me", self._scope, {"preview-me": 1}, {"preview-me": 1}
        )

    def _create_editor(self, bounds: QRect) -> PlacementDialog:
        display = ScoreboardDisplay()
        self._set_preview_content(display)
        preview = DraggablePreview(display)
        display.size_changed.connect(preview.fit_content)
        return PlacementDialog(
            bounds,
            bounds.topLeft(),
            preview,
            self._placement.corner,
            self.controls.window(),
            T("Déplacez le tableau à la souris, puis enregistrez sa position."),
        )

    def _update(self) -> None:
        if self._closing:
            return
        snapshot = self.live.state.snapshot
        if snapshot is not self._snapshot:
            self._snapshot = snapshot
            self._fresh = snapshot is not None
            if self._fresh:
                self._expiry.start()
            else:
                self._expiry.stop()
        self._refresh_window()
        self._toggle(self.controls.activation_enabled())

    def _expire(self) -> None:
        self._fresh = False
        self._toggle(self.controls.activation_enabled())

    def shutdown(self) -> None:
        self._expiry.stop()
        super().shutdown()
