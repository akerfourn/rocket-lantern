"""Tint the existing vector icon family without loading user-supplied assets."""

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from rocket_lantern.labels import ICON_FAMILIES, SYMBOLS, Label


@lru_cache(maxsize=256)
def colored_tag(symbol: str, color: str, family: str = "tag") -> QIcon:
    if symbol not in SYMBOLS:
        symbol = "tag"
    if family not in ICON_FAMILIES:
        family = "tag"
    if family != "tag":
        return _family_icon(family, symbol, color)
    path = Path(__file__).parent / "assets" / f"evaluation-{symbol}.svg"
    pixmap = QIcon(str(path)).pixmap(32, 32)
    painter = QPainter(pixmap)
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
    finally:
        painter.end()
    return QIcon(pixmap)


def label_icon(label: Label | None, family: str = "tag") -> QIcon:
    if label is None:
        return colored_tag("not_evaluated", "#aab1ba", family)
    return colored_tag(label.symbol, label.color, family)


def _family_icon(family: str, symbol: str, color: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(
                QColor(color),
                3,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        outline = QPainterPath()
        if family == "shield":
            outline.moveTo(32, 6)
            outline.lineTo(54, 14)
            outline.lineTo(51, 36)
            outline.quadTo(47, 50, 32, 58)
            outline.quadTo(17, 50, 13, 36)
            outline.lineTo(10, 14)
            outline.closeSubpath()
        else:
            painter.drawLine(QPointF(11, 7), QPointF(11, 58))
            outline.moveTo(11, 12)
            outline.cubicTo(27, 3, 38, 20, 55, 10)
            outline.lineTo(55, 42)
            outline.cubicTo(38, 52, 27, 35, 11, 44)
            outline.closeSubpath()
        painter.drawPath(outline)
        _draw_symbol(painter, symbol)
    finally:
        painter.end()
    return QIcon(pixmap)


def _draw_symbol(painter: QPainter, symbol: str) -> None:
    path = QPainterPath()
    if symbol == "not_evaluated":
        path.moveTo(24, 29)
        path.lineTo(41, 29)
    elif symbol == "no_suspicion":
        path.moveTo(23, 29)
        path.lineTo(30, 36)
        path.lineTo(43, 22)
    elif symbol == "possible":
        path.moveTo(26, 23)
        path.cubicTo(26, 14, 43, 15, 40, 24)
        path.cubicTo(39, 28, 33, 28, 33, 32)
        painter.drawPoint(QPointF(33, 39))
    elif symbol == "strong":
        path.moveTo(33, 19)
        path.lineTo(33, 32)
        painter.drawPoint(QPointF(33, 39))
    painter.drawPath(path)
