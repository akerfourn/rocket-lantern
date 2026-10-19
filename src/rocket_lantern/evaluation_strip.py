"""Independent icon-only menus for each active annotation list."""

from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from rocket_lantern.evaluation_button import EvaluationButton
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.labels import DEFAULT_LIST


class EvaluationStrip(QWidget):
    chosen = Signal(str, str, str)

    def __init__(
        self, catalog: LabelCatalog, parent: QWidget | None = None, history: bool = False
    ) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.history = history
        self.guid = ""
        self.choices: dict[str, str] = {}
        self.buttons: dict[str, EvaluationButton] = {}
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._sync_lists()
        catalog.changed.connect(self._sync_lists)

    def _sync_lists(self) -> None:
        for item in self.catalog.lists:
            if item.id not in self.buttons:
                button = EvaluationButton(self, self.catalog, item.id)
                button.selected.connect(partial(self._chosen, item.id))
                self.buttons[item.id] = button
            button = self.buttons[item.id]
            self._row.removeWidget(button)
            self._row.addWidget(button)
            visible = item.enabled or (self.history and item.id in self.choices)
            button.setVisible(visible)
        self.set_match(self.guid, self.choices)

    def _chosen(self, list_id: str, guid: str, value: str) -> None:
        self.chosen.emit(guid, list_id, value)

    def set_match(self, guid: str, choices: dict[str, str]) -> None:
        self.guid = guid
        self.choices = dict(choices)
        for list_id, button in self.buttons.items():
            group = next((item for item in self.catalog.lists if item.id == list_id), None)
            visible = group is not None and (group.enabled or (self.history and list_id in choices))
            button.setVisible(visible)
            value = choices.get(list_id, "")
            if list_id == DEFAULT_LIST and value == "":
                value = "not_evaluated"
            button.set_match(guid, value)

    def update_choice(self, guid: str, list_id: str, value: str) -> None:
        if guid == self.guid:
            self.choices[list_id] = value
            self.set_match(guid, self.choices)
