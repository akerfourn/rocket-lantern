"""Keep statistic icons centered independently of the native header's icon alignment."""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette
from PySide6.QtWidgets import QHeaderView, QStyle, QStyleOptionHeader, QWidget

ICON_SIZE = 20
ICON_MARGIN = 4


class StatHeader(QHeaderView):
    """Preserve native header sections while centering their icon-only contents."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)

    def sectionSizeFromContents(self, logical_index: int) -> QSize:
        size = super().sectionSizeFromContents(logical_index)
        model = self.model()
        if model is None:
            return size
        icon = model.headerData(logical_index, self.orientation(), Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            minimum = ICON_SIZE + 2 * ICON_MARGIN
            return size.expandedTo(QSize(minimum, minimum))
        return size

    def paintSection(self, painter: QPainter, rectangle: QRect, logical_index: int) -> None:
        if not rectangle.isValid():
            return
        option = QStyleOptionHeader()
        self.initStyleOption(option)
        self.initStyleOptionForIndex(option, logical_index)
        if option.icon.isNull():
            super().paintSection(painter, rectangle, logical_index)
            return
        icon = QIcon(option.icon)
        option.icon = QIcon()
        option.text = ""
        option.rect = rectangle
        painter.save()
        try:
            self.style().drawControl(QStyle.ControlElement.CE_Header, option, painter, self)
            size = min(ICON_SIZE, rectangle.width(), rectangle.height())
            icon_rectangle = QRect(0, 0, size, size)
            icon_rectangle.moveCenter(rectangle.center())
            pixmap = icon.pixmap(icon_rectangle.size(), self.devicePixelRatioF())
            tint = QPainter(pixmap)
            try:
                tint.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                tint.fillRect(pixmap.rect(), option.palette.color(QPalette.ColorRole.ButtonText))
            finally:
                tint.end()
            painter.drawPixmap(icon_rectangle.topLeft(), pixmap)
        finally:
            painter.restore()
