"""Global shortcut permission; individual bindings live in the category editor."""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class HotkeySettings(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox(T("Activer les raccourcis clavier globaux"))
        self.enabled.setChecked(True)
        layout.addWidget(self.enabled)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
