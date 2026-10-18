"""Opt-in boost HUD with explicit risk acknowledgment and independent placement."""

from PySide6.QtCore import QRect, QTimer
from PySide6.QtWidgets import QMessageBox, QWidget

from rocket_lantern.boost_overlay import BoostDisplay, BoostOverlay, TeammateBoost, teammate_boosts
from rocket_lantern.game_presence import GamePresenceMonitor
from rocket_lantern.i18n import text as T
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.match_data import MatchSnapshot
from rocket_lantern.overlay_controller import DesktopOverlayController
from rocket_lantern.overlay_placement_dialog import DraggablePreview, PlacementDialog
from rocket_lantern.overlay_settings import OverlaySettings, boost_warning
from rocket_lantern.storage import MatchStore


class BoostOverlayController(DesktopOverlayController):
    def __init__(
        self,
        controls: OverlaySettings,
        live: LiveMatchPanel,
        owner: QWidget,
        store: MatchStore,
        presence: GamePresenceMonitor | None = None,
    ) -> None:
        self.live = live
        self._risk_accepted = store.setting("boost_overlay_risk_accepted") == "1"
        self._readings: tuple[TeammateBoost, ...] = ()
        self._snapshot: MatchSnapshot | None = None
        self._fresh = False
        super().__init__(
            controls,
            owner,
            store,
            "boost_overlay_placement",
            "boost_overlay_enabled",
            "top_right",
            presence,
        )
        self._expiry = QTimer(self)
        self._expiry.setSingleShot(True)
        self._expiry.setInterval(3000)
        self._expiry.timeout.connect(self._expire)
        live.state_changed.connect(self._update)

    def _can_restore_activation(self) -> bool:
        return self._risk_accepted

    def _activation_settings(self, enabled: bool) -> dict[str, str]:
        values = super()._activation_settings(enabled)
        if enabled:
            values["boost_overlay_risk_accepted"] = "1"
        return values

    def _allow_activation(self) -> bool:
        if self._risk_accepted:
            return True
        question = T("Acceptez-vous ce risque et souhaitez-vous activer cet overlay ?")
        answer = QMessageBox.warning(
            self.controls.window(),
            str(T("Overlay de boost · avertissement")),
            str(boost_warning()) + "\n\n" + str(question),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        self._risk_accepted = answer == QMessageBox.StandardButton.Yes
        return self._risk_accepted

    def _has_content(self) -> bool:
        return self._fresh and bool(self._readings)

    def _create_window(self) -> BoostOverlay:
        return BoostOverlay()

    def _refresh_window(self) -> None:
        if isinstance(self.window, BoostOverlay):
            self.window.set_readings(self._readings)

    def _create_editor(self, bounds: QRect) -> PlacementDialog:
        display = BoostDisplay()
        # Fictional values exist only inside the explicit placement preview.
        display.set_readings(
            (
                TeammateBoost("preview-1", str(T("Coéquipier 1")), 75),
                TeammateBoost("preview-2", str(T("Coéquipier 2")), 20),
            )
        )
        return PlacementDialog(
            bounds,
            bounds.topLeft(),
            DraggablePreview(display),
            self._placement.corner,
            self.controls.window(),
            T("Aperçu fictif : déplacez les jauges, puis enregistrez leur position."),
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
        self._readings = teammate_boosts(self.live.state, self.live.player_id)
        self._refresh_window()
        self._toggle(self.controls.enabled.isChecked())

    def _expire(self) -> None:
        self._fresh = False
        self._readings = ()
        self._refresh_window()
        self._toggle(self.controls.enabled.isChecked())

    def shutdown(self) -> None:
        self._expiry.stop()
        super().shutdown()
