"""Explicit opt-in and configurable single-chord shortcuts for match assessments."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QFormLayout, QKeySequenceEdit, QVBoxLayout, QWidget

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
        self.fields = QWidget()
        self.form = QFormLayout(self.fields)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.editors: list[QKeySequenceEdit] = []
        self.label_ids: tuple[str, ...] = ()
        if catalog is None:
            catalog = LabelCatalog(parent=self)
        self.configure(catalog)
        self.fields.hide()
        self.enabled.toggled.connect(self.fields.setVisible)
        self.enabled.toggled.connect(self._changed)
        layout.addWidget(self.fields)
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
        while self.form.rowCount():
            self.form.removeRow(0)
        self.editors.clear()
        labels = []
        for group in catalog.enabled_lists():
            labels.extend(item for item in catalog.items(group.id) if item.enabled)
        self.label_ids = tuple(item.id for item in labels)
        groups = {item.id: item for item in catalog.enabled_lists()}
        for item in labels:
            editor = QKeySequenceEdit(QKeySequence(item.shortcut))
            editor.setMaximumSequenceLength(1)
            editor.setClearButtonEnabled(True)
            title = item.title
            if len(groups) > 1:
                title = T(
                    "{list_name} · {label}", list_name=groups[item.list_id].title, label=item.title
                )
            self.form.addRow(QLabel(title), editor)
            self.editors.append(editor)

    def _changed(self, enabled: bool) -> None:
        self.status.setText(T("Clique sur Appliquer les raccourcis pour enregistrer ce choix."))

    def sequences(self) -> tuple[str, ...]:
        return tuple(
            editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            for editor in self.editors
        )
