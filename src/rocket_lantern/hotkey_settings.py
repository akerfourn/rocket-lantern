"""Global shortcut opt-in; individual bindings live in the category editor."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class HotkeySettings(QGroupBox):
    apply_requested = Signal()

    def __init__(self, parent: QWidget, catalog: LabelCatalog | None = None) -> None:
        super().__init__(T("Raccourcis d’évaluation"), parent)
        layout = QVBoxLayout(self)
        self.enabled = QCheckBox(T("Activer les raccourcis clavier globaux"))
        layout.addWidget(self.enabled)
        self.label_ids: tuple[str, ...] = ()
        self._sequences: tuple[str, ...] = ()
        if catalog is None:
            catalog = LabelCatalog(parent=self)
        self.configure(catalog)
        self.enabled.toggled.connect(self._changed)
        self.apply_button = QPushButton(T("Appliquer les raccourcis"))
        self.apply_button.setAutoDefault(False)
        self.apply_button.clicked.connect(self.apply_requested)
        layout.addWidget(self.apply_button)
        self.status = QLabel(
            T("Raccourcis désactivés · l’évaluation à la souris reste disponible.")
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def configure(self, catalog: LabelCatalog) -> None:
        active = {group.id for group in catalog.enabled_lists()}
        labels = [
            item for item in catalog.labels.values() if item.enabled and item.list_id in active
        ]
        self.label_ids = tuple(item.id for item in labels)
        self._sequences = tuple(item.shortcut for item in labels)

    def _changed(self, enabled: bool) -> None:
        self.status.setText(T("Clique sur Appliquer les raccourcis pour enregistrer ce choix."))

    def sequences(self) -> tuple[str, ...]:
        return self._sequences
