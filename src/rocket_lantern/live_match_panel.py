"""Read-only current match view, independent of history filters and persistence."""

from dataclasses import astuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.live_match import LiveMatchState
from rocket_lantern.match_detail_dialog import display
from rocket_lantern.playlists import playlist_label
from rocket_lantern.statistics import STAT_LABELS


class LiveMatchPanel(QWidget):
    """Show the latest observed score, clock, ball and current participants."""

    def __init__(self, player_id: str) -> None:
        super().__init__()
        self.state = LiveMatchState()
        self._player_id = player_id
        self._table_signature: tuple[object, ...] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.phase = QLabel()
        self.phase.setWordWrap(True)
        layout.addWidget(self.phase)
        self.context = QLabel()
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        self.score = QLabel()
        self.score.setTextFormat(Qt.TextFormat.RichText)
        self.score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score.setStyleSheet("font-size: 30px; padding: 8px; font-weight: 600;")
        layout.addWidget(self.score)
        self.clock = QLabel()
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock.setStyleSheet("font-size: 23px; font-weight: 600;")
        layout.addWidget(self.clock)
        self.ball = QLabel()
        self.ball.setWordWrap(True)
        layout.addWidget(self.ball)
        self.boost_label = QLabel("Boost du joueur sélectionné : —")
        self.boost_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.boost_label)
        self.boost = QProgressBar()
        self.boost.setRange(0, 100)
        self.boost.setToolTip(
            "Affiché uniquement si le champ Boost est reçu pour ce joueur. "
            "Sa disponibilité dépend de la visibilité autorisée par le jeu."
        )
        layout.addWidget(self.boost)
        layout.addWidget(QLabel("Joueurs · compteurs du match (joueur sélectionné en gras)"))
        self.players = QTableWidget(0, 3 + len(STAT_LABELS))
        self.players.setHorizontalHeaderLabels(["Joueur", "Équipe", "Boost", *STAT_LABELS.values()])
        self.players.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.players.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.players.setAlternatingRowColors(True)
        self.players.setShowGrid(False)
        self.players.verticalHeader().hide()
        self.players.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.players.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.players, 1)
        note = QLabel(
            "Dernières valeurs reçues, sans extrapolation. — : donnée absente ; 0 : zéro reçu. "
            "Cette vue reste en mémoire et ne sauvegarde pas les mesures temps réel."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self._render()

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
        self.phase.setText(self.state.phase)
        if self.state.goal_replay:
            self.phase.setText("Ralenti de but · dernières données hors ralenti")
        snapshot = self.state.snapshot
        if snapshot is None:
            self.context.setText("Aucune partie en direct disponible")
            self.score.setText("Bleus — – — Oranges")
            self.clock.setText("—:—")
            self.ball.setText("Vitesse du ballon : — · dernière équipe au contact : —")
            self._render_boost()
            self.players.setRowCount(0)
            self._table_signature = None
            return
        self.context.setText(f"{playlist_label(snapshot.playlist)} · {display(snapshot.arena)}")
        player = snapshot.players.get(self._player_id)
        team = None
        if player is not None:
            team = player.team
        blue = display(snapshot.blue_score)
        orange = display(snapshot.orange_score)
        if team == 0:
            blue = f"<b><u>{blue}</u></b>"
        elif team == 1:
            orange = f"<b><u>{orange}</u></b>"
        self.score.setText(
            f'<span style="color:#2186c4">Bleus {blue}</span> – '
            f'<span style="color:#c87518">{orange} Oranges</span>'
        )
        clock = "—:—"
        if snapshot.time_seconds is not None:
            minutes, seconds = divmod(snapshot.time_seconds, 60)
            clock = f"{minutes}:{seconds:02d}"
        if snapshot.overtime is True:
            clock = f"Prolongation · +{clock}"
        self.clock.setText(clock)
        speed = "—"
        if self.state.ball_speed is not None:
            speed = f"{self.state.ball_speed:.0f} u/s"
        last_touch = {0: "équipe bleue", 1: "équipe orange"}.get(self.state.last_touch_team, "—")
        self.ball.setText(
            f"Vitesse du ballon : {speed} · dernière équipe au contact : {last_touch}"
        )
        self.ball.setToolTip("La vitesse est exprimée dans les unités Unreal par seconde de l’API.")
        self._render_boost()
        self._render_players()

    def _render_boost(self) -> None:
        value = self.state.boost.get(self._player_id)
        name = "joueur sélectionné"
        if self.state.snapshot is not None:
            player = self.state.snapshot.players.get(self._player_id)
            if player is not None:
                name = player.name
        self.boost_label.setText(f"Boost · {name}")
        self.boost.setEnabled(value is not None)
        if value is None:
            self.boost.setValue(0)
            self.boost.setFormat("— · champ non reçu")
        else:
            self.boost.setValue(value)
            self.boost.setFormat("%p %")

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
            values = [player.name, {0: "Bleue", 1: "Orange"}[player.team]]
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
                self.players.setItem(row, column, item)
