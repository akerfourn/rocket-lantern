"""An explicit, cancellable drag preview; the real HUD stays non-interactive."""

from PySide6.QtCore import QAbstractAnimation, QPoint, QRect, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QHideEvent, QMouseEvent, QPainter, QPaintEvent, QPen, QResizeEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QVBoxLayout, QWidget

from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.overlay_anchor_buttons import OverlayAnchorButtons
from rocket_lantern.overlay_placement import horizontal_anchor_offset
from rocket_lantern.storage import Summary
from rocket_lantern.summary_overlay import SummaryDisplay, overlay_position
from rocket_lantern.summary_overlay_content import SummaryOverlayContent
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class DraggablePreview(QWidget):
    """Wrap any HUD rendering with bounded mouse dragging for placement only."""

    geometry_changed = Signal()

    def __init__(self, display: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.display = display
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.set_opacity(100)
        self.horizontal_anchor = "left"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(display)
        self.fit_content()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._drag_offset: QPoint | None = None
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def fit_content(self) -> None:
        point = self.pos()
        offset = horizontal_anchor_offset(self.width(), self.horizontal_anchor)
        self.display.adjustSize()
        self.setFixedSize(self.display.size())
        if self.parentWidget() is not None:
            new_offset = horizontal_anchor_offset(self.width(), self.horizontal_anchor)
            self.place(point + QPoint(offset - new_offset, 0))

    def set_opacity(self, value: int) -> None:
        self.opacity_effect.setOpacity(value / 100)
        self.opacity_effect.setEnabled(value != 100)

    def place(self, point: QPoint) -> None:
        bounds = self.parentWidget().rect()
        self.move(
            max(0, min(point.x(), max(0, bounds.width() - self.width()))),
            max(0, min(point.y(), max(0, bounds.height() - self.height()))),
        )
        self.geometry_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            point = self.parentWidget().mapFromGlobal(event.globalPosition().toPoint())
            self.place(point - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class DraggableSummary(DraggablePreview):
    def __init__(self, parent: QWidget | None = None) -> None:
        display = SummaryDisplay()
        super().__init__(display, parent)
        self.wins = display.wins
        self.losses = display.losses
        self.balance = display.balance

    def set_summary(self, summary: Summary) -> None:
        self.display.set_summary(summary)
        self.fit_content()

    def set_content(
        self, content: SummaryOverlayContent, catalog: LabelCatalog, choices: dict[str, str]
    ) -> None:
        self.display.set_content(content, catalog, choices)
        self.fit_content()


class PlacementDialog(QDialog):
    """Cover the chosen screen with a tint and a same-size, draggable preview."""

    def __init__(
        self,
        bounds: QRect,
        position: QPoint,
        preview: DraggablePreview,
        corner: str,
        parent: QWidget,
        hint: DisplayText | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(T("Positionner l’overlay"))
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setGeometry(bounds)
        self._bounds = QRect(bounds)
        self._corner = corner
        self.preview = preview
        self.preview.setParent(self)
        self.preview.place(position - bounds.topLeft())
        self.locate_animation = QVariantAnimation(self)
        self.locate_animation.setDuration(800)
        self.locate_animation.setStartValue(0.0)
        self.locate_animation.setEndValue(1.0)
        self.locate_animation.valueChanged.connect(lambda value: self.update())
        self.locate_animation.finished.connect(self.update)
        self.toolbar = QWidget(self)
        self.toolbar.setObjectName("placementToolbar")
        self.toolbar.setStyleSheet(
            "#placementToolbar { background: #24272e; border: 1px solid #5c6370;"
            " border-radius: 8px; }"
            "#placementToolbar QLabel { color: #f3f4f6; }"
        )
        layout = QVBoxLayout(self.toolbar)
        if hint is None:
            hint = T("Déplacez le bandeau à la souris, puis enregistrez sa position.")
        label = QLabel(hint)
        label.setWordWrap(True)
        layout.addWidget(label)
        alignment = QHBoxLayout()
        self.anchor_label = QLabel(T("Ancrage horizontal :"))
        self.anchor_buttons = OverlayAnchorButtons()
        self.anchor_label.setToolTip(
            T("Point qui reste fixe lorsque la largeur de l’overlay change.")
        )
        self.anchor_label.setBuddy(self.anchor_buttons.buttons["left"])
        self.anchor_buttons.changed.connect(self._anchor_changed)
        alignment.addWidget(self.anchor_label)
        alignment.addWidget(self.anchor_buttons)
        alignment.addStretch()
        layout.addLayout(alignment)
        actions = QHBoxLayout()
        self.reset_button = QPushButton(T("Réinitialiser"))
        self.reset_button.setAutoDefault(False)
        self.reset_button.clicked.connect(self._reset)
        actions.addWidget(self.reset_button)
        self.locate_button = QPushButton(T("Repérer"))
        self.locate_button.setAutoDefault(False)
        self.locate_button.setToolTip(T("Afficher un repère animé autour de l’overlay."))
        self.locate_button.clicked.connect(self._locate_preview)
        actions.addWidget(self.locate_button)
        actions.addStretch()
        self.cancel_button = QPushButton(T("Annuler"))
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)
        self.save_button = QPushButton(T("Enregistrer"))
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.toolbar_opacity = QGraphicsOpacityEffect(self.toolbar)
        self.toolbar.setGraphicsEffect(self.toolbar_opacity)
        self.preview.geometry_changed.connect(self._update_toolbar_opacity)
        self._place_toolbar()

    def _reset(self) -> None:
        self.preview.place(overlay_position(self.rect(), self.preview.size(), self._corner))

    def set_horizontal_anchor(self, anchor: str) -> None:
        self.anchor_buttons.set_anchor(anchor)

    def _anchor_changed(self, anchor: str) -> None:
        self.preview.horizontal_anchor = anchor

    def _locate_preview(self) -> None:
        self.locate_animation.stop()
        self.locate_animation.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self.locate_animation.stop()
        super().hideEvent(event)

    def selected_position(self) -> QPoint:
        return self._bounds.topLeft() + self.preview.pos()

    def _place_toolbar(self) -> None:
        self.toolbar.setFixedWidth(min(500, max(1, self.width() - 32)))
        self.toolbar.adjustSize()
        self.toolbar.move(max(0, (self.width() - self.toolbar.width()) // 2), 16)
        self.toolbar.raise_()
        self._update_toolbar_opacity()

    def _update_toolbar_opacity(self) -> None:
        """Reveal the HUD under the controls without changing placement or hit targets."""
        opacity = 1.0
        if self.toolbar.geometry().intersects(self.preview.geometry()):
            opacity = 0.35
        self.toolbar_opacity.setOpacity(opacity)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toolbar"):
            self._place_toolbar()
            self.preview.place(self.preview.pos())

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
            if self.locate_animation.state() == QAbstractAnimation.State.Running:
                self._paint_locator(painter)
        finally:
            painter.end()

    def _paint_locator(self, painter: QPainter) -> None:
        """Pulse around the current preview geometry without changing its hit area."""
        phase = float(self.locate_animation.currentValue())
        spread = 8 + 44 * phase
        target = QRectF(self.preview.geometry())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 210, 65, 230), 3))
        painter.drawRoundedRect(target.adjusted(-4, -4, 4, 4), 10, 10)
        painter.setPen(QPen(QColor(255, 210, 65, int(200 * (1 - phase))), 3))
        painter.drawRoundedRect(target.adjusted(-spread, -spread, spread, spread), 14, 14)


class OverlayPlacementDialog(PlacementDialog):
    def __init__(
        self, bounds: QRect, position: QPoint, summary: Summary, corner: str, parent: QWidget
    ) -> None:
        preview = DraggableSummary()
        preview.set_summary(summary)
        super().__init__(bounds, position, preview, corner, parent)
