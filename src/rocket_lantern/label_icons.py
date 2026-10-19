"""Tint the existing vector icon family without loading user-supplied assets."""

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QColor, QIcon, QPainter

from rocket_lantern.labels import SYMBOLS, Label


@lru_cache(maxsize=256)
def colored_tag(symbol: str, color: str) -> QIcon:
    if symbol not in SYMBOLS:
        symbol = "tag"
    path = Path(__file__).parent / "assets" / f"evaluation-{symbol}.svg"
    pixmap = QIcon(str(path)).pixmap(32, 32)
    painter = QPainter(pixmap)
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
    finally:
        painter.end()
    return QIcon(pixmap)


def label_icon(label: Label | None) -> QIcon:
    if label is None:
        return colored_tag("not_evaluated", "#aab1ba")
    return colored_tag(label.symbol, label.color)
