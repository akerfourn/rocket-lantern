"""Live teammate-only HUD, using the same received values and gauges as the main view."""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout

from rocket_lantern.boost_gauge import BoostGauge
from rocket_lantern.i18n import text as T
from rocket_lantern.live_match import LiveMatchState
from rocket_lantern.summary_overlay import OverlayDisplay, configure_overlay
from rocket_lantern.translated_widgets import set_text


@dataclass(frozen=True)
class TeammateBoost:
    primary_id: str
    name: str
    value: int | None
    assume_empty: bool = False


def teammate_boosts(state: LiveMatchState, player_id: str) -> tuple[TeammateBoost, ...]:
    """Never infer a team or retain a departed teammate from an earlier packet."""
    snapshot = state.snapshot
    if snapshot is None or state.goal_replay or snapshot.final_observed:
        return ()
    if state.phase in ("Terminée · dernier état observé", "Podium · dernier état observé"):
        return ()
    selected = snapshot.players.get(player_id)
    if selected is None or selected.team not in (0, 1):
        return ()
    players = sorted(snapshot.players.values(), key=lambda player: (player.name, player.primary_id))
    readings = []
    for player in players:
        if player.team != selected.team or player.primary_id == player_id:
            continue
        readings.append(
            TeammateBoost(
                player.primary_id,
                player.name,
                state.boost.get(player.primary_id),
                player.primary_id in state.omitted_boost,
            )
        )
    return tuple(readings)


class BoostDisplay(OverlayDisplay):
    """Fixed-width, named gauges; rows are reused rather than recreated every tick."""

    def __init__(self) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(220)
        self.setStyleSheet("QLabel { color: #f3f4f6; font-size: 13px; font-weight: 600; }")
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(12, 10, 12, 10)
        self.rows.setSpacing(10)
        self.gauges: dict[str, BoostGauge] = {}

    def set_readings(self, readings: tuple[TeammateBoost, ...]) -> None:
        current_ids = {reading.primary_id for reading in readings}
        for primary_id in list(self.gauges):
            if primary_id not in current_ids:
                gauge = self.gauges.pop(primary_id)
                self.rows.removeWidget(gauge)
                gauge.hide()
                gauge.deleteLater()
        for index, reading in enumerate(readings):
            gauge = self.gauges.get(reading.primary_id)
            if gauge is None:
                gauge = BoostGauge()
                self.gauges[reading.primary_id] = gauge
            if self.rows.indexOf(gauge) != index:
                self.rows.insertWidget(index, gauge)
            gauge.set_boost(reading.name, reading.value, reading.assume_empty)
            gauge.show()
        self.rows.activate()
        self.setFixedHeight(self.rows.sizeHint().height())


class BoostOverlay(BoostDisplay):
    def __init__(self) -> None:
        super().__init__()
        configure_overlay(self)
        set_text(
            self, "windowTitle", T("RocketLantern · Boost des coéquipiers"), self.setWindowTitle
        )
