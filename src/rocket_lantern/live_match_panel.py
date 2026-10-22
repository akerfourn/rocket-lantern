"""Read-only current match view, independent of history filters and persistence."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.boost_gauge import BoostGauge
from rocket_lantern.i18n import text as T
from rocket_lantern.live_match import LiveMatchState
from rocket_lantern.live_match_status import LiveMatchStatus
from rocket_lantern.live_team_table import LiveTeamTable
from rocket_lantern.match_data import PlayerStats
from rocket_lantern.match_detail_dialog import display
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel

BOOST_SIDEBAR_WIDTH = 240
SIDE_BY_SIDE_MINIMUM_WIDTH = 900


class LiveMatchPanel(QWidget):
    """Give current participants most of the space below a compact score header."""

    boost_side_changed = Signal(str)
    state_changed = Signal()

    def __init__(self, player_id: str, boost_side: str = "left") -> None:
        super().__init__()
        self.state = LiveMatchState()
        self._player_id = player_id
        self._boost_layout_state: tuple[bool, str] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        self.header = QWidget()
        header = QGridLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setColumnStretch(0, 1)
        header.setColumnStretch(2, 1)
        self.status_indicator = LiveMatchStatus()
        header.addWidget(self.status_indicator, 0, 0, Qt.AlignmentFlag.AlignLeft)
        self.boost_controls = QWidget()
        boost_controls = QHBoxLayout(self.boost_controls)
        boost_controls.setContentsMargins(0, 0, 0, 0)
        boost_controls.addWidget(QLabel(T("Boosts :")))
        self.boost_side = QComboBox()
        self.boost_side.addItem(T("À gauche"), "left")
        self.boost_side.addItem(T("À droite"), "right")
        self.boost_side.setToolTip(T("Côté des jauges, mémorisé pour ce poste."))
        self.boost_side.setCurrentIndex(max(0, self.boost_side.findData(boost_side)))
        boost_controls.addWidget(self.boost_side)
        header.addWidget(self.boost_controls, 0, 2, Qt.AlignmentFlag.AlignRight)
        self.score = QLabel()
        self.score.setTextFormat(Qt.TextFormat.RichText)
        self.score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score.setStyleSheet("font-size: 30px; font-weight: 600;")
        self.clock = QLabel()
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock.setStyleSheet("font-size: 23px; font-weight: 600;")
        self.scoreboard = QWidget()
        scoreboard = QHBoxLayout(self.scoreboard)
        scoreboard.setContentsMargins(0, 0, 0, 0)
        scoreboard.setSpacing(24)
        scoreboard.addWidget(self.score)
        scoreboard.addWidget(self.clock)
        header.addWidget(self.scoreboard, 0, 1, Qt.AlignmentFlag.AlignCenter)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.header)
        for label in (self.score, self.clock):
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.boost_dock = QGroupBox(T("Boost"))
        self.boost_dock.setFixedWidth(BOOST_SIDEBAR_WIDTH)
        dock_layout = QVBoxLayout(self.boost_dock)
        dock_layout.setSpacing(14)
        self.selected_boost = BoostGauge(muted=True)
        self.boost_label = self.selected_boost.name
        self.boost = self.selected_boost.bar
        self.teammates = QWidget()
        self._teammates_layout = QVBoxLayout(self.teammates)
        self._teammates_layout.setContentsMargins(0, 0, 0, 0)
        self._teammates_layout.setSpacing(14)
        self.teammates_hint = QLabel()
        self.teammates_hint.setWordWrap(True)
        self._teammates_layout.addWidget(self.teammates_hint)
        self.teammate_gauges: dict[str, BoostGauge] = {}
        dock_layout.addWidget(self.teammates)
        dock_layout.addWidget(self.selected_boost)
        self.teammates.show()
        self.selected_boost.show()
        self.player_area = QWidget()
        player_layout = QVBoxLayout(self.player_area)
        player_layout.setContentsMargins(0, 0, 0, 0)
        self.players = LiveTeamTable()
        player_layout.addWidget(self.players, 1)
        self.content = QWidget()
        self._content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(16)
        self._content_layout.addWidget(self.boost_dock)
        self._content_layout.addWidget(self.player_area, 1)
        layout.addWidget(self.content, 1)
        self.boost_side.currentIndexChanged.connect(self._change_boost_side)
        self._arrange_boosts()
        self._render()

    def _change_boost_side(self, index: int) -> None:
        self._arrange_boosts()
        self.boost_side_changed.emit(self.boost_side.currentData())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._arrange_boosts()

    def _arrange_boosts(self) -> None:
        self.boost_dock.setMinimumHeight(self.boost_dock.minimumSizeHint().height())
        side = self.boost_side.currentData()
        wide = self.width() >= SIDE_BY_SIDE_MINIMUM_WIDTH
        minimum_height = max(
            self.boost_dock.minimumHeight(), self.player_area.minimumSizeHint().height()
        )
        if not wide:
            minimum_height = (
                self.boost_dock.minimumHeight()
                + self._content_layout.spacing()
                + self.player_area.minimumSizeHint().height()
            )
        self.content.setMinimumHeight(minimum_height)
        if self._boost_layout_state == (wide, side):
            return
        self._boost_layout_state = (wide, side)
        direction = QBoxLayout.Direction.TopToBottom
        alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        if side == "right":
            alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        if wide:
            direction = QBoxLayout.Direction.LeftToRight
            if side == "right":
                direction = QBoxLayout.Direction.RightToLeft
        self._content_layout.setDirection(direction)
        self._content_layout.setAlignment(self.boost_dock, alignment)

    def observe(self, message: dict[str, object], observed_at: str, history_replay: bool) -> None:
        """Update the current match even without a selected player or saved result."""
        self.state.observe(message, observed_at, history_replay)
        self._render()
        self.state_changed.emit()

    def set_player(self, player_id: str) -> None:
        """Change score emphasis immediately without attributing a stored result."""
        self._player_id = player_id
        self._render()
        self.state_changed.emit()

    @property
    def player_id(self) -> str:
        return self._player_id

    def clear(self, reason: str) -> None:
        """Remove stale scores and participant values when observation stops."""
        self.state.clear(reason)
        self._render()
        self.state_changed.emit()

    def _render(self) -> None:
        self.status_indicator.update_state(self.state, self._player_id)
        self._render_clock()
        snapshot = self.state.snapshot
        if snapshot is None:
            self._render_score("—", "—", None)
            self._render_boost()
            self.players.clear_players()
            return
        player = snapshot.players.get(self._player_id)
        team = None
        if player is not None:
            team = player.team
        blue = display(snapshot.blue_score)
        orange = display(snapshot.orange_score)
        self._render_score(blue, orange, team)
        self._render_boost()
        self._render_players()

    def _render_clock(self) -> None:
        snapshot = self.state.snapshot
        clock = "—:—"
        if snapshot is not None and snapshot.time_seconds is not None:
            minutes, seconds = divmod(snapshot.time_seconds, 60)
            clock = f"{minutes}:{seconds:02d}"
        description = T("Temps restant : {clock}", clock=clock)
        if snapshot is not None and snapshot.overtime is True:
            description = T("Prolongation · +{clock}", clock=clock)
            clock = f"+{clock}"
        self.clock.setText(clock)
        self.clock.setToolTip(description)
        self.clock.setAccessibleName(description)

    def _render_score(self, blue: str, orange: str, team: int | None) -> None:
        self.score.setAccessibleName(
            T("Équipe bleue {blue} ; équipe orange {orange}", blue=blue, orange=orange)
        )
        self.score.setToolTip(T("Équipe bleue à gauche ; équipe orange à droite."))
        if team == 0:
            blue = f"<b><u>{blue}</u></b>"
        elif team == 1:
            orange = f"<b><u>{orange}</u></b>"
        self.score.setText(
            f'<span style="color:#2186c4">● {blue}</span> – '
            f'<span style="color:#c87518">{orange} ●</span>'
        )

    def _render_boost(self) -> None:
        value = self.state.boost.get(self._player_id)
        name = T("joueur sélectionné")
        if self.state.snapshot is not None:
            player = self.state.snapshot.players.get(self._player_id)
            if player is not None:
                name = player.name
        self.selected_boost.set_boost(T("{name} · sélectionné", name=name), value)
        self._render_teammates()

    def _render_teammates(self) -> None:
        snapshot = self.state.snapshot
        selected = None
        if snapshot is not None:
            selected = snapshot.players.get(self._player_id)
        teammates: list[PlayerStats] = []
        hint = T("Sélectionne un joueur présent pour afficher ses coéquipiers.")
        if snapshot is None:
            hint = T("En attente d’une partie en direct.")
        elif selected is not None:
            teammates = [
                player
                for player in snapshot.players.values()
                if player.team == selected.team and player.primary_id != self._player_id
            ]
            teammates.sort(key=lambda player: (player.name, player.primary_id))
            hint = T("Aucun coéquipier présent dans cette partie.")
        current_ids = {player.primary_id for player in teammates}
        for primary_id in list(self.teammate_gauges):
            if primary_id not in current_ids:
                gauge = self.teammate_gauges.pop(primary_id)
                self._teammates_layout.removeWidget(gauge)
                gauge.hide()
                gauge.deleteLater()
        self.teammates_hint.setText(hint)
        self.teammates_hint.setVisible(len(teammates) == 0)
        for index, player in enumerate(teammates):
            gauge = self.teammate_gauges.get(player.primary_id)
            if gauge is None:
                gauge = BoostGauge()
                self.teammate_gauges[player.primary_id] = gauge
            if self._teammates_layout.indexOf(gauge) != index + 1:
                self._teammates_layout.insertWidget(index + 1, gauge)
            gauge.show()
            gauge.set_boost(
                player.name,
                self.state.boost.get(player.primary_id),
                assume_empty=player.primary_id in self.state.omitted_boost,
            )
        self._arrange_boosts()

    def _render_players(self) -> None:
        snapshot = self.state.snapshot
        if snapshot is None:
            return
        self.players.update_players(
            list(snapshot.players.values()),
            self._player_id,
            self.state.epic_saves,
            opponent_post_hits=self.state.opponent_post_hits,
        )
