"""Read-only current match view, independent of history filters and persistence."""

from dataclasses import astuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.boost_gauge import BoostGauge
from rocket_lantern.i18n import text as T
from rocket_lantern.live_match import LiveMatchState
from rocket_lantern.match_data import PlayerStats
from rocket_lantern.match_detail_dialog import display
from rocket_lantern.playlists import playlist_text as playlist_label
from rocket_lantern.statistics import STAT_LABELS
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedItem as QTableWidgetItem
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget

BOOST_SIDEBAR_WIDTH = 240
SIDE_BY_SIDE_MINIMUM_WIDTH = 900


class LiveMatchPanel(QWidget):
    """Show the latest observed score, clock, ball and current participants."""

    boost_side_changed = Signal(str)

    def __init__(self, player_id: str, boost_side: str = "left") -> None:
        super().__init__()
        self.state = LiveMatchState()
        self._player_id = player_id
        self._table_signature: tuple[object, ...] | None = None
        self._boost_layout_state: tuple[bool, str] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        self.phase = QLabel()
        self.phase.setWordWrap(True)
        header = QHBoxLayout()
        header.addWidget(self.phase, 1)
        header.addWidget(QLabel(T("Boosts :")))
        self.boost_side = QComboBox()
        self.boost_side.addItem(T("À gauche"), "left")
        self.boost_side.addItem(T("À droite"), "right")
        self.boost_side.setToolTip(T("Côté des jauges, mémorisé pour ce poste."))
        self.boost_side.setCurrentIndex(max(0, self.boost_side.findData(boost_side)))
        header.addWidget(self.boost_side)
        layout.addLayout(header)
        self.context = QLabel()
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        self.score = QLabel()
        self.score.setTextFormat(Qt.TextFormat.RichText)
        self.score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score.setStyleSheet("font-size: 30px; padding: 4px; font-weight: 600;")
        self.clock = QLabel()
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock.setStyleSheet("font-size: 23px; font-weight: 600;")
        scoreboard = QHBoxLayout()
        scoreboard.setSpacing(24)
        scoreboard.addStretch()
        scoreboard.addWidget(self.score)
        scoreboard.addWidget(self.clock)
        scoreboard.addStretch()
        layout.addLayout(scoreboard)
        self.ball = QLabel()
        self.ball.setWordWrap(True)
        layout.addWidget(self.ball)
        for label in (self.phase, self.context, self.score, self.clock, self.ball):
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
        player_layout.addWidget(QLabel(T("Joueurs · sélection en gras")))
        self.players = QTableWidget(0, 3 + len(STAT_LABELS))
        self.players.setHorizontalHeaderLabels(
            [T("Joueur"), T("Équipe"), T("Boost"), *[T(value) for value in STAT_LABELS.values()]]
        )
        self.players.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.players.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.players.setAlternatingRowColors(True)
        self.players.setShowGrid(False)
        self.players.verticalHeader().hide()
        self.players.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.players.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        player_layout.addWidget(self.players, 1)
        self.content = QWidget()
        self._content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(16)
        self._content_layout.addWidget(self.boost_dock)
        self._content_layout.addWidget(self.player_area, 1)
        layout.addWidget(self.content, 1)
        note = QLabel(
            T(
                "— : donnée absente ; 0 : zéro reçu ; ≈ 0 : boost d’un coéquipier "
                "omis, assimilé à zéro pour l’alerte. Cette vue reste en mémoire "
                "et ne sauvegarde pas les mesures temps réel."
            )
        )
        note.setWordWrap(True)
        note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout.addWidget(note)
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

    def set_player(self, player_id: str) -> None:
        """Change score emphasis immediately without attributing a stored result."""
        self._player_id = player_id
        self._render()

    def clear(self, reason: str) -> None:
        """Remove stale scores and participant values when observation stops."""
        self.state.clear(reason)
        self._render()

    def _render(self) -> None:
        self.phase.setText(T(self.state.phase))
        if self.state.goal_replay:
            self.phase.setText(T("Ralenti de but · dernières données hors ralenti"))
        snapshot = self.state.snapshot
        if snapshot is None:
            self.context.setText(T("Aucune partie en direct disponible"))
            self._render_score("—", "—", None)
            self.clock.setText("—:—")
            self.ball.setText(T("Vitesse du ballon : — · dernière équipe au contact : —"))
            self._render_boost()
            self.players.setRowCount(0)
            self._table_signature = None
            return
        self.context.setText(
            T(
                "{playlist} · {arena}",
                playlist=playlist_label(snapshot.playlist),
                arena=display(snapshot.arena),
            )
        )
        player = snapshot.players.get(self._player_id)
        team = None
        if player is not None:
            team = player.team
        blue = display(snapshot.blue_score)
        orange = display(snapshot.orange_score)
        self._render_score(blue, orange, team)
        clock = "—:—"
        if snapshot.time_seconds is not None:
            minutes, seconds = divmod(snapshot.time_seconds, 60)
            clock = f"{minutes}:{seconds:02d}"
        if snapshot.overtime is True:
            clock = T("Prolongation · +{clock}", clock=clock)
        self.clock.setText(clock)
        speed = "—"
        if self.state.ball_speed is not None:
            speed = f"{self.state.ball_speed:.0f} u/s"
        last_touch = {0: T("équipe bleue"), 1: T("équipe orange")}.get(
            self.state.last_touch_team, "—"
        )
        self.ball.setText(
            T(
                "Vitesse du ballon : {speed} · dernière équipe au contact : {last_touch}",
                speed=speed,
                last_touch=last_touch,
            )
        )
        self.ball.setToolTip(
            T("La vitesse est exprimée dans les unités Unreal par seconde de l’API.")
        )
        self._render_boost()
        self._render_players()

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
        players = sorted(snapshot.players.values(), key=lambda player: (player.team, player.name))
        signature = (
            self._player_id,
            tuple(astuple(player) for player in players),
            tuple(self.state.boost.items()),
        )
        if signature == self._table_signature:
            return
        self._table_signature = signature
        self.players.setRowCount(len(players))
        for row, player in enumerate(players):
            values = [player.name, "●"]
            boost = self.state.boost.get(player.primary_id)
            boost_text = "—"
            if boost is not None:
                boost_text = f"{boost} %"
            values.append(boost_text)
            values.extend(display(getattr(player, field)) for field in STAT_LABELS)
            font = QFont(self.players.font())
            font.setBold(player.primary_id == self._player_id)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFont(font)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, player.primary_id)
                elif column == 1:
                    team_name = {0: T("Équipe bleue"), 1: T("Équipe orange")}[player.team]
                    item.setForeground(QColor({0: "#2186c4", 1: "#c87518"}[player.team]))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(team_name)
                    item.setData(Qt.ItemDataRole.AccessibleTextRole, team_name)
                self.players.setItem(row, column, item)
