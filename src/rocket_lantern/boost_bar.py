"""Progress bar with an explicit moving-stripe loading indicator for empty boost."""

from PySide6.QtCore import QAbstractAnimation, QPointF, QRectF, QVariantAnimation
from PySide6.QtGui import QColor, QHideEvent, QPainter, QPainterPath, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import QProgressBar


class BoostBar(QProgressBar):
    """Animate only a visible empty teammate gauge, independently of native themes."""

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self._phase = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(24.0)
        self.animation.setDuration(900)
        self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self._advance)

    def set_loading(self, enabled: bool) -> None:
        """Keep repeated zero packets from restarting the animation."""
        self._loading = enabled
        self._sync_animation()
        self.update()

    def _sync_animation(self) -> None:
        running = self.animation.state() == QAbstractAnimation.State.Running
        if self._loading and self.isVisible():
            if not running:
                self.animation.start()
        elif running:
            self.animation.stop()

    def _advance(self, value: object) -> None:
        if isinstance(value, float):
            self._phase = value
            self.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._sync_animation()

    def hideEvent(self, event: QHideEvent) -> None:
        self.animation.stop()
        super().hideEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._loading:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            path = QPainterPath()
            path.addRoundedRect(bounds, 3, 3)
            painter.setClipPath(path)
            painter.fillRect(bounds, QColor("#b54242"))
            painter.setPen(QPen(QColor(255, 255, 255, 65), 8))
            for offset in range(-48, self.width() + 48, 24):
                x = offset + self._phase
                painter.drawLine(QPointF(x, bounds.bottom()), QPointF(x + 16, bounds.top()))
        finally:
            painter.end()
