"""Accessible tag buttons with a manual assessment menu."""

from functools import partial
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from rocket_lantern.evaluations import Evaluation, evaluation_label
from rocket_lantern.i18n import render
from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import binding, set_text, tooltip


def evaluation_icon(value: Evaluation) -> QIcon:
    """Use vector tags with different symbols, not color alone."""
    path = Path(__file__).parent / "assets" / f"evaluation-{value.value}.svg"
    return QIcon(str(path))


class EvaluationButton(QToolButton):
    selected = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.guid = ""
        self._menu_guid = ""
        self.value = Evaluation.NOT_EVALUATED
        self.setIconSize(QSize(28, 28))
        self.setFixedSize(40, 32)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu = QMenu(self)
        self._action_group = QActionGroup(self._menu)
        self.actions_by_value: dict[Evaluation, QAction] = {}
        for value in Evaluation:
            action = self._menu.addAction(evaluation_icon(value), render(evaluation_label(value)))
            action.setCheckable(True)
            self._action_group.addAction(action)
            action.triggered.connect(partial(self._select, value))
            self.actions_by_value[value] = action
        self._menu.aboutToShow.connect(self._capture_match)
        self.clicked.connect(self._show_menu)
        binding(self).callbacks.append(self._translate_actions)
        self.set_match("", self.value)

    def _translate_actions(self) -> None:
        for value, action in self.actions_by_value.items():
            action.setText(render(evaluation_label(value)))

    def _show_menu(self) -> None:
        self._menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def _capture_match(self) -> None:
        self._menu_guid = self.guid
        for value, action in self.actions_by_value.items():
            action.setChecked(value == self.value)

    def _select(self, value: Evaluation, checked: bool = False) -> None:
        if self._menu_guid:
            self.selected.emit(self._menu_guid, value.value)

    def set_match(self, guid: str, value: Evaluation) -> None:
        """Keep the target explicit; an open menu never switches to another match."""
        if self.guid != guid:
            self._menu.close()
        self.guid = guid
        self.value = value
        self.setEnabled(guid != "")
        self.setIcon(evaluation_icon(value))
        tooltip(
            self,
            T(
                "{evaluation} · évaluation personnelle du match. Clique pour modifier.",
                evaluation=evaluation_label(value),
            ),
        )
        set_text(self, "accessibleName", evaluation_label(value), self.setAccessibleName)
        for state, action in self.actions_by_value.items():
            action.setChecked(state == value)
