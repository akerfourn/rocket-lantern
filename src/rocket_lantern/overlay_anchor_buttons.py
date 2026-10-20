"""Compact, mutually exclusive horizontal alignment controls for overlay placement."""

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QToolButton, QWidget

from rocket_lantern.i18n import text as T
from rocket_lantern.overlay_placement import HORIZONTAL_ANCHORS
from rocket_lantern.translated_widgets import set_text, tooltip


def alignment_icon(anchor: str) -> QIcon:
    """Draw familiar text-alignment lines with separate checked-state artwork."""
    icon = QIcon()
    for state, color in ((QIcon.State.Off, "#dbe0e7"), (QIcon.State.On, "#ffffff")):
        pixmap = QPixmap(40, 40)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for index, width in enumerate((14, 9, 14, 11)):
                left = 3.0
                if anchor == "center":
                    left = (20 - width) / 2
                elif anchor == "right":
                    left = 17 - width
                y = 4 + index * 4
                painter.drawLine(QPointF(left, y), QPointF(left + width, y))
        finally:
            painter.end()
        icon.addPixmap(pixmap, QIcon.Mode.Normal, state)
    return icon


class OverlayAnchorButtons(QWidget):
    """Offer icon-only left, center and right choices with accessible translated names."""

    changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "QToolButton { background: #30343d; border: 1px solid #626b79;"
            " border-radius: 0; }"
            "QToolButton:hover { background: #424956; }"
            "QToolButton:checked { background: #1976b8; }"
            "QToolButton:focus { border-color: #a8d4ff; }"
            "QToolButton#left { border-top-left-radius: 4px; border-bottom-left-radius: 4px; }"
            "QToolButton#center { border-left: 0; }"
            "QToolButton#right { border-left: 0; border-top-right-radius: 4px;"
            " border-bottom-right-radius: 4px; }"
        )
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for index, (anchor, label) in enumerate(
            (("left", T("Gauche")), ("center", T("Centre")), ("right", T("Droite")))
        ):
            button = QToolButton(self)
            button.setObjectName(anchor)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIcon(alignment_icon(anchor))
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(32, 28)
            tooltip(button, label)
            set_text(button, "accessibleName", label, button.setAccessibleName)
            self.buttons[anchor] = button
            self.group.addButton(button, index)
            layout.addWidget(button)
        self.buttons["left"].setChecked(True)
        self.group.buttonToggled.connect(self._selection_changed)

    def selected_anchor(self) -> str:
        return HORIZONTAL_ANCHORS[self.group.checkedId()]

    def set_anchor(self, anchor: str) -> None:
        if anchor not in self.buttons:
            raise ValueError("Invalid horizontal overlay anchor")
        self.buttons[anchor].setChecked(True)

    def _selection_changed(self, button: QAbstractButton, checked: bool) -> None:
        if checked:
            self.changed.emit(self.selected_anchor())
