"""Native Qt widgets retaining explicit text sources for in-place LanguageChange."""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)

from rocket_lantern.i18n import DateText, DisplayText, Text, render


class TextBinding(QObject):
    """Update only explicitly registered properties; never infer translations from data."""

    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self.setObjectName("translationBinding")
        self.properties: dict[str, tuple[DisplayText, Callable[[str], None]]] = {}
        self.callbacks: list[Callable[[], None]] = []
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.LanguageChange:
            for source, setter in list(self.properties.values()):
                setter(render(source))
            for callback in self.callbacks:
                callback()
        return False


def binding(widget: QWidget) -> TextBinding:
    result = widget.findChild(
        TextBinding, "translationBinding", Qt.FindChildOption.FindDirectChildrenOnly
    )
    if result is None:
        result = TextBinding(widget)
    return result


def set_text(widget: QWidget, key: str, value: DisplayText, setter: Callable[[str], None]) -> None:
    properties = binding(widget).properties
    if isinstance(value, (Text, DateText)):
        properties[key] = (value, setter)
    else:
        properties.pop(key, None)
    setter(render(value))


def tooltip(widget: QWidget, value: DisplayText) -> None:
    set_text(widget, "tooltip", value, lambda rendered: QWidget.setToolTip(widget, rendered))


class TranslatedLabel(QLabel):
    def __init__(self, value: DisplayText = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(value)

    def setText(self, value: DisplayText) -> None:
        set_text(self, "text", value, super().setText)

    def setToolTip(self, value: DisplayText) -> None:
        tooltip(self, value)

    def setAccessibleName(self, value: DisplayText) -> None:
        set_text(self, "accessibleName", value, super().setAccessibleName)


class TranslatedButton(QPushButton):
    def __init__(self, value: DisplayText = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(value)

    def setText(self, value: DisplayText) -> None:
        set_text(self, "text", value, super().setText)

    def setToolTip(self, value: DisplayText) -> None:
        tooltip(self, value)


class TranslatedCheckBox(QCheckBox):
    def __init__(self, value: DisplayText = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(value)

    def setText(self, value: DisplayText) -> None:
        set_text(self, "text", value, super().setText)


class TranslatedGroupBox(QGroupBox):
    def __init__(self, value: DisplayText = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(value)

    def setTitle(self, value: DisplayText) -> None:
        set_text(self, "title", value, super().setTitle)


class TranslatedDialog(QDialog):
    def setWindowTitle(self, value: DisplayText) -> None:
        set_text(self, "windowTitle", value, super().setWindowTitle)


class TranslatedComboBox(QComboBox):
    def addItem(self, value: DisplayText, userData: object = None) -> None:
        super().addItem(render(value), userData)
        self.setItemText(self.count() - 1, value)

    def setItemText(self, index: int, value: DisplayText) -> None:
        def apply(rendered: str) -> None:
            with QSignalBlocker(self):
                QComboBox.setItemText(self, index, rendered)

        set_text(self, f"item:{index}", value, apply)

    def clear(self) -> None:
        properties = binding(self).properties
        for key in list(properties):
            if key.startswith("item:"):
                del properties[key]
        super().clear()

    def setToolTip(self, value: DisplayText) -> None:
        tooltip(self, value)


class TranslatedTabWidget(QTabWidget):
    def addTab(self, widget: QWidget, value: DisplayText) -> int:
        index = super().addTab(widget, render(value))
        set_text(self, f"tab:{index}", value, lambda rendered: self.setTabText(index, rendered))
        return index


class TranslatedItem(QTableWidgetItem):
    def __init__(self, value: DisplayText = "") -> None:
        super().__init__()
        self.source: DisplayText = ""
        self.tip: DisplayText = ""
        self.accessible: DisplayText = ""
        self.setText(value)

    def setText(self, value: DisplayText) -> None:
        self.source = value
        super().setText(render(value))

    def setToolTip(self, value: DisplayText) -> None:
        self.tip = value
        super().setToolTip(render(value))

    def retranslate(self) -> None:
        super().setText(render(self.source))
        super().setToolTip(render(self.tip))
        if self.accessible != "":
            super().setData(Qt.ItemDataRole.AccessibleTextRole, render(self.accessible))

    def setData(self, role: int, value: object) -> None:
        if role == Qt.ItemDataRole.AccessibleTextRole and isinstance(value, (Text, DateText)):
            self.accessible = value
            value = render(value)
        super().setData(role, value)


class TranslatedTable(QTableWidget):
    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        binding(self).callbacks.append(self._retranslate)

    def setHorizontalHeaderLabels(self, labels: Sequence[DisplayText]) -> None:
        for column, label in enumerate(labels):
            self.setHorizontalHeaderItem(column, TranslatedItem(label))

    def _retranslate(self) -> None:
        for column in range(self.columnCount()):
            header = self.horizontalHeaderItem(column)
            if isinstance(header, TranslatedItem):
                header.retranslate()
            for row in range(self.rowCount()):
                item = self.item(row, column)
                if isinstance(item, TranslatedItem):
                    item.retranslate()
