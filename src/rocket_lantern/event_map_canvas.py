"""Interactive 3D event projection using Qt's existing software painter."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from rocket_lantern.event_map_data import MapEvent, Position
from rocket_lantern.i18n import text as T
from rocket_lantern.map_projection import (
    CEILING,
    FLOOR,
    SIDE_WALL,
    MapCamera,
    MapProjection,
    goal_vertices,
)
from rocket_lantern.translated_widgets import set_text, tooltip


class EventMapCanvas(QWidget):
    """Project actual XYZ points, depth-sort them and highlight the selected occurrence."""

    event_selected = Signal(object)

    def __init__(self, points: tuple[MapEvent, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.points = points
        self.selected_id: int | None = None
        self.camera = MapCamera()
        self._press: QPointF | None = None
        self._last: QPointF | None = None
        self._dragged = False
        self._drag_button: Qt.MouseButton | None = None
        self._panning = False
        self.setMinimumSize(260, 240)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        set_text(self, "accessibleName", T("Carte 3D des événements"), self.setAccessibleName)
        tooltip(
            self,
            T(
                "Glisser avec le bouton gauche pour pivoter ; "
                "bouton droit ou Maj pour déplacer le centre. "
                "Molette pour zoomer. "
                "Cliquer sur un point pour le sélectionner."
            ),
        )

    def set_points(self, points: tuple[MapEvent, ...]) -> None:
        self.points = points
        if not any(point.event_id == self.selected_id for point in points):
            self.selected_id = None
        self.update()

    def select_event(self, event_id: int | None) -> None:
        self.selected_id = event_id
        self.update()

    def reset_view(self) -> None:
        self.camera = MapCamera()
        self.update()

    def top_view(self) -> None:
        self.camera.yaw = 0
        self.camera.elevation = 90
        self.update()

    def focus_on(self, position: Position) -> None:
        """Choose the orbit pivot without changing angle, zoom or event selection."""
        self.camera.target = position
        self.update()

    def projection(self) -> MapProjection:
        return MapProjection.fit(
            self.camera, tuple(point.position for point in self.points), self.width(), self.height()
        )

    def hit_test(self, position: QPointF) -> int | None:
        projection = self.projection()
        candidates = []
        for point in self.points:
            x, y, depth = projection.project(point.position)
            distance = math.hypot(x - position.x(), y - position.y())
            if distance <= 10:
                candidates.append((distance, -depth, point.event_id))
        if not candidates:
            return None
        return min(candidates)[2]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), QColor("#171d26"))
            projection = self.projection()
            self._paint_arena(painter, projection)
            if self.camera.target is not None:
                self._paint_pivot(painter)
            ordered = sorted(self.points, key=lambda point: projection.project(point.position)[2])
            selected = None
            for point in ordered:
                if point.event_id == self.selected_id:
                    selected = point
                else:
                    self._paint_point(painter, projection, point)
            if selected is not None:
                self._paint_point(painter, projection, selected, selected=True)
            self._paint_axes(painter)
        finally:
            painter.end()

    @staticmethod
    def _polygon(projection: MapProjection, positions: tuple[Position, ...]) -> QPolygonF:
        return QPolygonF([QPointF(*projection.project(position)[:2]) for position in positions])

    def _line(
        self, painter: QPainter, projection: MapProjection, start: Position, end: Position
    ) -> None:
        painter.drawLine(
            QPointF(*projection.project(start)[:2]), QPointF(*projection.project(end)[:2])
        )

    def _paint_arena(self, painter: QPainter, projection: MapProjection) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#203545"))
        painter.drawPolygon(
            self._polygon(projection, FLOOR[:4] + ((SIDE_WALL, 0, 0), (-SIDE_WALL, 0, 0)))
        )
        painter.setBrush(QColor("#3b302a"))
        painter.drawPolygon(
            self._polygon(projection, FLOOR[4:] + ((-SIDE_WALL, 0, 0), (SIDE_WALL, 0, 0)))
        )
        painter.setPen(QPen(QColor("#485362"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(self._polygon(projection, FLOOR))
        for x, y, z in FLOOR:
            self._line(painter, projection, (x, y, z), (x, y, CEILING))
        painter.setPen(QPen(QColor("#3b4553"), 1, Qt.PenStyle.DashLine))
        painter.drawPolygon(self._polygon(projection, tuple((x, y, CEILING) for x, y, _ in FLOOR)))
        painter.setPen(QPen(QColor("#8391a1"), 1))
        self._line(painter, projection, (-SIDE_WALL, 0, 0), (SIDE_WALL, 0, 0))
        circle = tuple(
            (920 * math.cos(i * math.tau / 64), 920 * math.sin(i * math.tau / 64), 0)
            for i in range(65)
        )
        painter.drawPolyline(self._polygon(projection, circle))
        for team, color in ((0, "#419bdf"), (1, "#e49a43")):
            vertices = goal_vertices(team)
            painter.setPen(QPen(QColor(color), 2))
            painter.drawPolygon(self._polygon(projection, vertices[:4]))
            painter.setPen(QPen(QColor(color), 1, Qt.PenStyle.DashLine))
            painter.drawPolygon(self._polygon(projection, vertices[4:]))
            for index in range(4):
                self._line(painter, projection, vertices[index], vertices[index + 4])

    def _paint_point(
        self,
        painter: QPainter,
        projection: MapProjection,
        point: MapEvent,
        *,
        selected: bool = False,
    ) -> None:
        x, y, _ = projection.project(point.position)
        center = QPointF(x, y)
        radius = 4.5
        if selected:
            radius = 7
            painter.setPen(QPen(QColor("#f8dd7c"), 1.5, Qt.PenStyle.DashLine))
            ground = (point.position[0], point.position[1], 0)
            self._line(painter, projection, ground, point.position)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawEllipse(center, 12, 12)
        painter.setPen(QPen(QColor("#111820"), 1.4))
        painter.setBrush(QColor(point.color))
        if point.kind == "GoalScored":
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, y - radius - 1),
                        QPointF(x + radius + 1, y),
                        QPointF(x, y + radius + 1),
                        QPointF(x - radius - 1, y),
                    ]
                )
            )
        elif point.position_subject == "boost_pickup":
            painter.drawRect(QRectF(x - radius, y - radius, 2 * radius, 2 * radius))
        else:
            painter.drawEllipse(center, radius, radius)

    def _paint_axes(self, painter: QPainter) -> None:
        origin = QPointF(36, self.height() - 32)
        base_x, base_y, _ = self.camera.project((0, 0, 0))
        for label, position, color in (
            ("X", (6000, 0, 0), "#ef9991"),
            ("Y", (0, 6000, 0), "#8accab"),
            ("Z", (0, 0, 6000), "#7cbbef"),
        ):
            x, y, _ = self.camera.project(position)
            tip = origin + QPointF((x - base_x) * 24, (y - base_y) * 24)
            painter.setPen(QPen(QColor(color), 1.5))
            painter.drawLine(origin, tip)
            painter.drawText(tip + QPointF(3, 0), label)

    def _paint_pivot(self, painter: QPainter) -> None:
        center = QPointF(self.width() / 2, self.height() / 2)
        painter.setPen(QPen(QColor("#a7b1c0"), 1))
        painter.drawLine(center + QPointF(-6, 0), center + QPointF(6, 0))
        painter.drawLine(center + QPointF(0, -6), center + QPointF(0, 6))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() not in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.MiddleButton,
        ):
            super().mousePressEvent(event)
            return
        self.setFocus()
        self._press = event.position()
        self._last = event.position()
        self._dragged = False
        self._drag_button = event.button()
        self._panning = event.button() != Qt.MouseButton.LeftButton or bool(
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        )
        if self._panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press is None or self._last is None:
            super().mouseMoveEvent(event)
            return
        offset = event.position() - self._last
        if (event.position() - self._press).manhattanLength() > 4:
            self._dragged = True
        if self._dragged:
            if self._panning:
                self.camera.target = self.projection().panned_target(offset.x(), offset.y())
            else:
                self.camera.rotate(offset.x() * 0.5, -offset.y() * 0.5)
            self.update()
        self._last = event.position()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == self._drag_button and self._press is not None:
            if not self._dragged and not self._panning:
                self.event_selected.emit(self.hit_test(event.position()))
            self._press = None
            self._last = None
            self._drag_button = None
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        self.camera.zoom_by(1.2 ** max(-4, min(4, delta / 120)))
        self.update()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        rotations = {
            Qt.Key.Key_Left: (-10, 0),
            Qt.Key.Key_Right: (10, 0),
            Qt.Key.Key_Up: (0, 5),
            Qt.Key.Key_Down: (0, -5),
        }
        if event.key() in rotations:
            self.camera.rotate(*rotations[event.key()])
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.camera.zoom_by(1.2)
        elif event.key() == Qt.Key.Key_Minus:
            self.camera.zoom_by(1 / 1.2)
        elif event.key() == Qt.Key.Key_Escape:
            self.event_selected.emit(None)
        else:
            super().keyPressEvent(event)
            return
        self.update()
        event.accept()
