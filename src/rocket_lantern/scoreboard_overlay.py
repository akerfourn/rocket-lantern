"""Compact, click-through live scoreboard using the main table's icons and team totals."""

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QAbstractItemView, QFrame, QVBoxLayout

from rocket_lantern.i18n import text as T
from rocket_lantern.live_team_table import LiveTeamTable
from rocket_lantern.match_data import PlayerStats
from rocket_lantern.scoreboard_overlay_scope import ScoreboardScope, scoreboard_players
from rocket_lantern.summary_overlay import OverlayDisplay, configure_overlay
from rocket_lantern.translated_widgets import binding, set_text


class ScoreboardDisplay(OverlayDisplay):
    """Fit actual table contents without scrollbars or repeated layout work on boost-only ticks."""

    size_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.players = LiveTeamTable()
        font = QFont(self.players.font())
        font.setPixelSize(13)
        self.players.setFont(font)
        palette = self.players.palette()
        for role in (
            QPalette.ColorRole.Text,
            QPalette.ColorRole.WindowText,
            QPalette.ColorRole.ButtonText,
        ):
            palette.setColor(role, QColor("#f3f4f6"))
        palette.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.Button, QColor("#252b35"))
        self.players.setPalette(palette)
        self.players.setStyleSheet(
            "QTableWidget { background: transparent; border: none; }"
            "QHeaderView::section { background: #252b35; color: #f3f4f6; border: none; }"
        )
        self.players.setFrameShape(QFrame.Shape.NoFrame)
        self.players.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.players.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.players.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.players.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.players.viewport().setAutoFillBackground(False)
        self.players.verticalHeader().setDefaultSectionSize(25)
        self.players.horizontalHeader().setFixedHeight(28)
        self.players.horizontalHeader().setMaximumSectionSize(180)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(self.players)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._fit_table)
        self.players.horizontalHeader().sectionResized.connect(self._queue_fit)
        binding(self).callbacks.append(self._queue_fit)

    def set_players(
        self,
        players: Sequence[PlayerStats],
        player_id: str,
        scope: ScoreboardScope,
        epic_saves: Mapping[str, int],
        post_hits: Mapping[str, int],
    ) -> None:
        readings = scoreboard_players(players, player_id, scope)
        changed = self.players.update_players(
            readings,
            player_id,
            epic_saves,
            opponent_post_hits=post_hits,
            show_team_totals=scope != ScoreboardScope.PLAYER,
        )
        if changed:
            self._fit_table()

    def _queue_fit(self) -> None:
        self._resize_timer.start(0)

    def _fit_table(self) -> None:
        self.players.resizeColumnsToContents()
        width = self.players.horizontalHeader().length() + 2 * self.players.frameWidth()
        height = self.players.verticalHeader().length() + self.players.horizontalHeader().height()
        height += 2 * self.players.frameWidth()
        self.players.setFixedSize(width, height)
        size = QSize(width + 20, height + 16)
        if self.size() != size:
            self.setFixedSize(size)
            self.size_changed.emit()


class ScoreboardOverlay(ScoreboardDisplay):
    def __init__(self) -> None:
        super().__init__()
        configure_overlay(self)
        set_text(self, "windowTitle", T("RocketLantern · Tableau des scores"), self.setWindowTitle)
