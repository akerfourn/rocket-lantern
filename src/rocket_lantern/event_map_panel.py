"""Linked read-only list and 3D projection of positioned match events."""

from collections.abc import Callable
from html import escape

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.event_map_canvas import EventMapCanvas
from rocket_lantern.event_map_data import MapEvent
from rocket_lantern.i18n import DisplayText, render
from rocket_lantern.i18n import text as T
from rocket_lantern.map_projection import BACK_WALL, GOAL_HEIGHT
from rocket_lantern.translated_widgets import TranslatedItem as QTableWidgetItem
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget
from rocket_lantern.translated_widgets import binding

type ClockFormatter = Callable[[int | None, bool], DisplayText]


def event_name(kind: str) -> DisplayText:
    return {
        "BallHit": T("Touche de balle"),
        "GoalScored": T("But"),
        "CrossbarHit": T("Barre"),
        "BoostPickup": T("Ramassage de boost"),
    }.get(kind, kind)


def player_icon(color: str) -> QIcon:
    image = QPixmap(16, 16)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#17202b"), 1))
        painter.setBrush(QColor(color))
        painter.drawEllipse(2, 2, 12, 12)
    finally:
        painter.end()
    return QIcon(image)


class EventMapPanel(QWidget):
    """Use the same stored occurrence ID for the list, map and external selection."""

    event_selected = Signal(object)

    def __init__(
        self,
        points: tuple[MapEvent, ...],
        clock_formatter: ClockFormatter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.points = points
        self._rows = {point.event_id: row for row, point in enumerate(points)}
        self._clock_formatter = clock_formatter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._build_toolbar()
        layout.addWidget(self.toolbar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        map_side = QWidget()
        map_layout = QVBoxLayout(map_side)
        map_layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = EventMapCanvas(points)
        map_layout.addWidget(self.canvas, 1)
        self.legend = QLabel()
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.legend.setWordWrap(True)
        self._update_legend()
        binding(self.legend).callbacks.append(self._update_legend)
        map_layout.addWidget(self.legend)
        self.position = QLabel()
        self.position.setTextFormat(Qt.TextFormat.PlainText)
        self.position.setWordWrap(True)
        map_layout.addWidget(self.position)
        self.splitter.addWidget(map_side)
        list_side = QWidget()
        list_layout = QVBoxLayout(list_side)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(QLabel(T("{count} événements positionnés", count=len(points))))
        self.events = self._event_table()
        list_layout.addWidget(self.events, 1)
        self.splitter.addWidget(list_side)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([650, 340])
        layout.addWidget(self.splitter, 1)
        self.canvas.event_selected.connect(self._canvas_selected)
        self.events.itemSelectionChanged.connect(self._list_selected)
        self.select_event(None)

    def _build_toolbar(self) -> None:
        """Keep camera controls on one line, with native action overflow on narrow windows."""
        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._action_texts: list[tuple[QAction, DisplayText, DisplayText]] = []
        self.toolbar.addWidget(QLabel(T("Centrer sur :")))
        self.center_button = self._add_action(
            T("Centre"), self._center_field, T("Centre du terrain")
        )
        self.blue_goal_button = self._add_action(T("Cage bleue"), self._center_blue_goal)
        self.orange_goal_button = self._add_action(T("Cage orange"), self._center_orange_goal)
        self.selected_button = self._add_action(
            T("Sélection"), self._center_selected, T("Événement sélectionné")
        )
        self.toolbar.addSeparator()
        self.top_button = self._add_action(T("Vue du dessus"), self._top_view)
        self.reset_button = self._add_action(T("Réinitialiser la vue"), self._reset_view)
        self._translate_actions()
        binding(self.toolbar).callbacks.append(self._translate_actions)

    def _add_action(
        self, text: DisplayText, callback: Callable[[], None], tip: DisplayText | None = None
    ) -> QToolButton:
        action = QAction(self.toolbar)
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        if tip is None:
            tip = text
        self._action_texts.append((action, text, tip))
        button = self.toolbar.widgetForAction(action)
        if not isinstance(button, QToolButton):
            raise RuntimeError("Map toolbar action has no tool button")
        return button

    def _translate_actions(self) -> None:
        for action, text, tip in self._action_texts:
            action.setText(render(text))
            action.setToolTip(render(tip))

    def _update_legend(self) -> None:
        teams: dict[int | None, dict[str | None, tuple[str, str]]] = {}
        for point in self.points:
            name = point.actor_name or render(T("Auteur inconnu"))
            if point.actor_key is None:
                name = render(T("Auteur inconnu"))
            players = teams.setdefault(point.actor_team, {})
            players.setdefault(point.actor_key, (name, point.color))
        groups = []
        for team, title, color in (
            (0, T("Équipe bleue"), "#56b4e9"),
            (1, T("Équipe orange"), "#e69f00"),
            (None, T("Équipe inconnue"), "#a8afb8"),
        ):
            players = teams.get(team, {})
            if not players:
                continue
            labels = [
                f'<span style="color:{player_color}">●</span> {escape(name)}'
                for name, player_color in players.values()
            ]
            groups.append(
                f'<td valign="top" style="border-left:3px solid {color}; padding:2px 8px;">'
                f'<b style="color:{color}">{escape(render(title))}</b><br>'
                + " &nbsp; · &nbsp; ".join(labels)
                + "</td>"
            )
        if not groups:
            self.legend.clear()
            return
        self.legend.setText(
            '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
            + "".join(groups)
            + "</tr></table>"
        )

    def _event_table(self) -> QTableWidget:
        widget = QTableWidget(len(self.points), 3)
        widget.setHorizontalHeaderLabels([T("Horloge"), T("Événement"), T("Joueur")])
        widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        widget.setAlternatingRowColors(True)
        widget.setShowGrid(False)
        widget.verticalHeader().hide()
        widget.verticalHeader().setDefaultSectionSize(30)
        widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for row, point in enumerate(self.points):
            clock = QTableWidgetItem(self._clock_formatter(point.time_seconds, point.overtime))
            clock.setData(Qt.ItemDataRole.UserRole, point.event_id)
            widget.setItem(row, 0, clock)
            widget.setItem(row, 1, QTableWidgetItem(event_name(point.kind)))
            name: DisplayText = point.actor_name or T("Auteur inconnu")
            if len(point.participant_names) > 1 and point.kind == "BallHit":
                name = " + ".join(point.participant_names)
            player = QTableWidgetItem(name)
            player.setIcon(player_icon(point.color))
            widget.setItem(row, 2, player)
        return widget

    def refresh_clocks(self) -> None:
        for row, point in enumerate(self.points):
            self.events.item(row, 0).setText(
                self._clock_formatter(point.time_seconds, point.overtime)
            )

    def select_event(self, event_id: int | None, *, notify: bool = False) -> None:
        row = self._rows.get(event_id)
        action = self.selected_button.defaultAction()
        if action is not None:
            action.setEnabled(row is not None)
        with QSignalBlocker(self.events):
            if row is None:
                event_id = None
                self.events.clearSelection()
                self.events.setCurrentCell(-1, -1)
            else:
                self.events.selectRow(row)
                self.events.scrollToItem(self.events.item(row, 0))
        self.canvas.select_event(event_id)
        if row is None:
            hint = T("Sélectionnez un événement pour afficher sa position.")
            if not self.points:
                hint = T("Aucun événement avec une position enregistrée pour ce match.")
            self.position.setText(hint)
        else:
            point = self.points[row]
            subject = {
                "ball": T("Ballon"),
                "boost_pickup": T("Point de boost"),
            }.get(point.position_subject, T("Position"))
            x, y, z = point.position
            self.position.setText(
                T(
                    "{subject} · X {x:.1f} · Y {y:.1f} · Z {z:.1f} uu",
                    subject=subject,
                    x=x,
                    y=y,
                    z=z,
                )
            )
        if notify:
            self.event_selected.emit(event_id)

    def _canvas_selected(self, event_id: int | None) -> None:
        self.select_event(event_id, notify=True)

    def _center_field(self) -> None:
        self.canvas.focus_on((0, 0, 0))

    def _top_view(self) -> None:
        self.canvas.top_view()

    def _reset_view(self) -> None:
        self.canvas.reset_view()

    def _center_blue_goal(self) -> None:
        self.canvas.focus_on((0, -BACK_WALL, GOAL_HEIGHT / 2))

    def _center_orange_goal(self) -> None:
        self.canvas.focus_on((0, BACK_WALL, GOAL_HEIGHT / 2))

    def _center_selected(self) -> None:
        row = self._rows.get(self.canvas.selected_id)
        if row is not None:
            self.canvas.focus_on(self.points[row].position)

    def _list_selected(self) -> None:
        row = self.events.currentRow()
        event_id = None
        if row >= 0 and self.events.selectedItems():
            event_id = self.points[row].event_id
        self.select_event(event_id, notify=True)
