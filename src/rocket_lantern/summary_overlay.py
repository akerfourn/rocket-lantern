"""Small, non-interactive desktop overlay; never hook or inject into the game."""

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from rocket_lantern.i18n import text as T
from rocket_lantern.result_summary import balance_icon, outcome_icon
from rocket_lantern.storage import Summary
from rocket_lantern.translated_widgets import binding, set_text


def overlay_position(bounds: QRect, size: QSize, corner: str, margin: int = 20) -> QPoint:
    """Place a compact HUD inside a screen, including monitors with negative coordinates."""
    left = bounds.left() + margin
    top = bounds.top() + margin
    right = bounds.left() + bounds.width() - size.width() - margin
    bottom = bounds.top() + bounds.height() - size.height() - margin
    x = left
    y = top
    if corner in ("top_right", "bottom_right"):
        x = right
    if corner in ("bottom_left", "bottom_right"):
        y = bottom
    x = max(bounds.left(), min(x, bounds.left() + max(0, bounds.width() - size.width())))
    y = max(bounds.top(), min(y, bounds.top() + max(0, bounds.height() - size.height())))
    return QPoint(x, y)


class OverlayDisplay(QWidget):
    """Shared translucent background for the desktop HUDs and placement previews."""

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(15, 18, 24, 215))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 0, -1, -1), 8, 8)
        finally:
            painter.end()


def configure_overlay(window: QWidget) -> None:
    """Do not steal focus or mouse input from the game, even while being shown."""
    window.setWindowFlags(
        Qt.WindowType.Tool
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.WindowTransparentForInput
        | Qt.WindowType.WindowDoesNotAcceptFocus
    )
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    window.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    window.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
    window.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class SummaryDisplay(OverlayDisplay):
    """Shared compact rendering for the click-through HUD and its interactive preview."""

    def __init__(
        self, parent: QWidget | None = None, flags: Qt.WindowType = Qt.WindowType.Widget
    ) -> None:
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("QLabel { color: #f3f4f6; font-size: 22px; font-weight: 600; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self._add_symbol(layout, outcome_icon("win").pixmap(22, 22))
        self.wins = QLabel()
        layout.addWidget(self.wins)
        layout.addSpacing(8)
        self._add_symbol(layout, outcome_icon("loss").pixmap(22, 22))
        self.losses = QLabel()
        layout.addWidget(self.losses)
        layout.addSpacing(8)
        self._balance_icons = {value: balance_icon(value) for value in (-1, 0, 1)}
        self.balance_symbol = QLabel()
        self.balance_symbol.setFixedSize(22, 22)
        layout.addWidget(self.balance_symbol)
        self.balance = QLabel()
        layout.addWidget(self.balance)
        self._summary = Summary(0, 0, 0)
        binding(self).callbacks.append(self._update_accessibility)
        self.set_summary(self._summary)

    @staticmethod
    def _add_symbol(layout: QHBoxLayout, pixmap: QPixmap) -> None:
        symbol = QLabel()
        symbol.setFixedSize(22, 22)
        symbol.setPixmap(pixmap)
        layout.addWidget(symbol)

    def set_summary(self, summary: Summary) -> None:
        """Display the same persisted, filtered results as the application banner."""
        self._summary = summary
        balance = summary.wins - summary.losses
        direction = 0
        if balance > 0:
            direction = 1
        elif balance < 0:
            direction = -1
        self.wins.setText(str(summary.wins))
        self.losses.setText(str(summary.losses))
        self.balance.setText(f"{balance:+d}")
        self.balance_symbol.setPixmap(self._balance_icons[direction].pixmap(22, 22))
        self._update_accessibility()
        self.adjustSize()

    def _update_accessibility(self) -> None:
        self.setAccessibleName(
            str(
                T(
                    "{wins} victoires · {losses} défaites · delta {balance}",
                    wins=self._summary.wins,
                    losses=self._summary.losses,
                    balance=f"{self._summary.wins - self._summary.losses:+d}",
                )
            )
        )


class SummaryOverlay(SummaryDisplay):
    """Unowned, click-through tool window independent of main-window minimization."""

    def __init__(self) -> None:
        super().__init__()
        configure_overlay(self)
        set_text(self, "windowTitle", T("RocketLantern · Overlay"), self.setWindowTitle)
