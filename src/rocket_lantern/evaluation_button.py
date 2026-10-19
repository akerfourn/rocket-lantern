"""Accessible tag buttons with a manual assessment menu."""

from functools import partial
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from rocket_lantern.evaluations import Evaluation
from rocket_lantern.i18n import render
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.label_icons import label_icon
from rocket_lantern.labels import DEFAULT_LIST
from rocket_lantern.translated_widgets import binding, set_text, tooltip


def evaluation_icon(value: Evaluation) -> QIcon:
    """Use vector tags with different symbols, not color alone."""
    path = Path(__file__).parent / "assets" / f"evaluation-{value.value}.svg"
    return QIcon(str(path))


class EvaluationButton(QToolButton):
    selected = Signal(str, str)

    def __init__(
        self,
        parent: QWidget | None = None,
        catalog: LabelCatalog | None = None,
        list_id: str = DEFAULT_LIST,
    ) -> None:
        super().__init__(parent)
        self.catalog = catalog
        if self.catalog is None:
            self.catalog = LabelCatalog(parent=self)
        self.list_id = list_id
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
        self.actions_by_value: dict[str, QAction] = {}
        self._build_actions()
        self._menu.aboutToShow.connect(self._capture_match)
        self.clicked.connect(self._show_menu)
        binding(self).callbacks.append(self._translate_actions)
        self.catalog.changed.connect(self._catalog_changed)
        self.set_match("", self.value)

    def _translate_actions(self) -> None:
        for value, action in self.actions_by_value.items():
            label = self.catalog.labels.get(value)
            title = T("Non évalué")
            if label is not None:
                title = label.title
            action.setText(render(title))

    def _build_actions(self) -> None:
        self._menu.clear()
        self.actions_by_value.clear()
        items = self.catalog.items(self.list_id)
        default = self.catalog.labels.get("not_evaluated")
        if self.list_id != DEFAULT_LIST or default is None or not default.enabled:
            self._add_action("", render(T("Non évalué")))
        for item in items:
            self._add_action(item.id, render(item.title))

    def _add_action(self, value: str, title: str) -> None:
        definition = self.catalog.labels.get(value)
        action = self._menu.addAction(label_icon(definition), title)
        action.setCheckable(True)
        if definition is not None:
            action.setEnabled(definition.enabled)
        self._action_group.addAction(action)
        action.triggered.connect(partial(self._select, value))
        self.actions_by_value[value] = action

    def _catalog_changed(self) -> None:
        self._menu.close()
        self._build_actions()
        self.set_match(self.guid, self.value)

    def _show_menu(self) -> None:
        self._menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def _capture_match(self) -> None:
        self._menu_guid = self.guid
        for value, action in self.actions_by_value.items():
            action.setChecked(value == self.value)

    def _select(self, value: str, checked: bool = False) -> None:
        if self._menu_guid:
            self.selected.emit(self._menu_guid, value)

    def set_match(self, guid: str, value: str) -> None:
        """Keep the target explicit; an open menu never switches to another match."""
        if self.guid != guid:
            self._menu.close()
        self.guid = guid
        self.value = value
        group = next((item for item in self.catalog.lists if item.id == self.list_id), None)
        self.setEnabled(guid != "" and group is not None and group.enabled)
        label = self.catalog.labels.get(value)
        title = T("Non évalué")
        if label is not None:
            title = label.title
        elif value not in ("", "not_evaluated"):
            title = value
        self.setIcon(label_icon(label))
        description = title
        if self.list_id != DEFAULT_LIST and group is not None:
            description = T("{list_name} · {label}", list_name=group.title, label=title)
        tooltip(
            self,
            T(
                "{evaluation} · évaluation personnelle du match. Clique pour modifier.",
                evaluation=description,
            ),
        )
        set_text(self, "accessibleName", title, self.setAccessibleName)
        for state, action in self.actions_by_value.items():
            action.setChecked(state == value)
