"""Display the shared statistic SVGs using the current label color and screen scale."""

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette

from rocket_lantern.branding import ASSET_DIRECTORY
from rocket_lantern.i18n import text as T
from rocket_lantern.statistics import STAT_LABELS
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel

ICON_SIZE = 20


class StatIcon(QLabel):
    """Keep summary icons legible in both light and dark palettes."""

    def __init__(self, field: str) -> None:
        super().__init__()
        self._icon = QIcon(str(ASSET_DIRECTORY / f"stat-{field}.svg"))
        self.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName(T(STAT_LABELS[field]))
        self._render()

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.DevicePixelRatioChange):
            self._render()
        return handled

    def _render(self) -> None:
        pixmap = self._icon.pixmap(QSize(ICON_SIZE, ICON_SIZE), self.devicePixelRatioF())
        if pixmap.isNull():
            self.clear()
            return
        painter = QPainter(pixmap)
        try:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            painter.fillRect(pixmap.rect(), self.palette().color(QPalette.ColorRole.WindowText))
        finally:
            painter.end()
        self.setPixmap(pixmap)
