"""Combine a team's stripe and an optional recognition symbol without adding a column."""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from rocket_lantern.branding import ASSET_DIRECTORY
from rocket_lantern.player_encounters import EncounterScope

ICON_WIDTH = 26
ICON_HEIGHT = 16
ENCOUNTER_COLORS = {
    EncounterScope.SESSION: "#28a98d",
    EncounterScope.HISTORY: "#8391a5",
}


def player_encounter_icon(team_color: str, scope: EncounterScope | None) -> QIcon:
    """Reserve the same compact icon space for all player names; retain the team stripe."""
    canvas = QPixmap(ICON_WIDTH * 2, ICON_HEIGHT * 2)
    canvas.setDevicePixelRatio(2)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    try:
        painter.fillRect(QRect(0, 0, 3, ICON_HEIGHT), QColor(team_color))
        if scope is not None:
            icon = QIcon(str(ASSET_DIRECTORY / "player-seen.svg"))
            symbol = icon.pixmap(QSize(ICON_HEIGHT, ICON_HEIGHT), 2)
            tint = QPainter(symbol)
            try:
                tint.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                tint.fillRect(symbol.rect(), QColor(ENCOUNTER_COLORS[scope]))
            finally:
                tint.end()
            painter.drawPixmap(QPoint(8, 0), symbol)
    finally:
        painter.end()
    return QIcon(canvas)
