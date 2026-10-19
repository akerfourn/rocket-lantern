"""One shared, refreshable catalog for settings, menus and keyboard bindings."""

from PySide6.QtCore import QObject, Signal

from rocket_lantern.label_repository import LabelRepository
from rocket_lantern.labels import DEFAULT_LIST, Label, LabelList, default_labels


class LabelCatalog(QObject):
    changed = Signal()

    def __init__(
        self, repository: LabelRepository | None = None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.lists = (LabelList(DEFAULT_LIST, "Suspicion de smurf"),)
        self.labels = {item.id: item for item in default_labels()}
        if repository is not None:
            self.reload()

    def reload(self) -> None:
        if self.repository is None:
            return
        lists = self.repository.lists()
        labels = {item.id: item for item in self.repository.labels()}
        if lists != self.lists or labels != self.labels:
            self.lists = lists
            self.labels = labels
            self.changed.emit()

    def items(self, list_id: str) -> tuple[Label, ...]:
        return tuple(item for item in self.labels.values() if item.list_id == list_id)

    def enabled_lists(self) -> tuple[LabelList, ...]:
        return tuple(item for item in self.lists if item.enabled)

    def bindings(self) -> dict[str, str]:
        active = {item.id for item in self.enabled_lists()}
        return {
            item.id: item.shortcut
            for item in self.labels.values()
            if item.enabled and item.list_id in active and item.shortcut != ""
        }
