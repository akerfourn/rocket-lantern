"""Compact, accessible live-view context without a permanent text banner."""

from typing import Literal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

from rocket_lantern.i18n import text as T
from rocket_lantern.live_match import LiveMatchState
from rocket_lantern.match_detail_dialog import display
from rocket_lantern.playlists import playlist_text
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel

type LiveView = Literal["waiting", "blue", "orange", "overview"]


def view_symbol(view: LiveView) -> QPixmap:
    """Draw a waiting clock or a team-colored eye without depending on symbol fonts."""
    pixmap = QPixmap(56, 56)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    color = QColor({"blue": "#56b4e9", "orange": "#e69f00"}.get(view, "#a8afb8"))
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if view == "waiting":
            painter.drawEllipse(QRectF(5, 5, 18, 18))
            painter.drawLine(QPointF(14, 8), QPointF(14, 14))
            painter.drawLine(QPointF(14, 14), QPointF(18, 16))
        else:
            eye = QPainterPath(QPointF(3, 14))
            eye.quadTo(14, 2, 25, 14)
            eye.quadTo(14, 26, 3, 14)
            painter.drawPath(eye)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(11, 11, 6, 6))
    finally:
        painter.end()
    return pixmap


class LiveMatchStatus(QLabel):
    """Keep phase, playlist and arena available on hover and to screen readers."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._symbols = {
            view: view_symbol(view) for view in ("waiting", "blue", "orange", "overview")
        }
        self.view_mode: LiveView = "waiting"
        self.setPixmap(self._symbols[self.view_mode])

    def update_state(self, state: LiveMatchState, player_id: str) -> None:
        """Use the tracked player's team; absence alone does not prove spectator mode."""
        phase = T(state.phase)
        if state.goal_replay:
            phase = T("Ralenti de but · dernières données hors ralenti")
        snapshot = state.snapshot
        if snapshot is None:
            self._set_view("waiting")
            description = T(
                "{view}\n{phase}", view=T("Aucune partie en direct disponible"), phase=phase
            )
        else:
            player = snapshot.players.get(player_id)
            view = T("Vue d’ensemble")
            mode: LiveView = "overview"
            if player is not None and player.team == 0:
                view = T("Équipe bleue")
                mode = "blue"
            elif player is not None and player.team == 1:
                view = T("Équipe orange")
                mode = "orange"
            self._set_view(mode)
            context = T(
                "{playlist} · {arena}",
                playlist=playlist_text(snapshot.playlist),
                arena=display(snapshot.arena),
            )
            description = T("{view}\n{phase}\n{context}", view=view, phase=phase, context=context)
        self.setToolTip(description)
        self.setAccessibleName(description)

    def _set_view(self, view: LiveView) -> None:
        if self.view_mode != view:
            self.view_mode = view
            self.setPixmap(self._symbols[view])
