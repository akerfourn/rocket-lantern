"""Edit one sound rule with event-specific subject wording and a live preview."""

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.i18n import text as T
from rocket_lantern.sound_alerts import (
    SCOPE_LABELS,
    SUBJECT_LABELS,
    TRIGGER_LABELS,
    WINDOWS_SOUNDS,
    PlayerScope,
    SoundKind,
    SoundRef,
    SoundRule,
    SoundTrigger,
)
from rocket_lantern.sound_library import SoundLibrary, sound_title
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class SoundRuleDialog(QDialog):
    preview_requested = Signal(object)

    def __init__(
        self,
        rule: SoundRule | None,
        sounds: tuple[SoundRef, ...],
        library: SoundLibrary,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.library = library
        self.identifier = str(uuid4())
        if rule is not None:
            self.identifier = rule.id
        self.setWindowTitle(T("Alerte sonore"))
        self.resize(510, 260)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.trigger = QComboBox()
        for trigger, title in TRIGGER_LABELS.items():
            self.trigger.addItem(title, trigger.value)
        form.addRow(QLabel(T("Déclencheur :")), self.trigger)
        self.subject_label = QLabel()
        self.scope = QComboBox()
        for scope, title in SCOPE_LABELS.items():
            self.scope.addItem(title, scope.value)
        self.subject_label.setBuddy(self.scope)
        form.addRow(self.subject_label, self.scope)
        self.sound = QComboBox()
        self.sound.setMinimumContentsLength(20)
        self.sound.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        for value in WINDOWS_SOUNDS:
            self._add_sound(SoundRef(SoundKind.WINDOWS, value))
        for sound in sounds:
            self._add_sound(sound)
        sound_row = QHBoxLayout()
        sound_row.addWidget(self.sound, 1)
        self.test_button = QPushButton(T("Tester"))
        self.test_button.clicked.connect(self._preview)
        sound_row.addWidget(self.test_button)
        form.addRow(QLabel(T("Son :")), sound_row)
        self.import_button = QPushButton(T("Importer un fichier audio…"))
        self.import_button.clicked.connect(self._import)
        form.addRow(self.import_button)
        self.enabled = QCheckBox(T("Alerte active"))
        self.enabled.setChecked(rule is None or rule.enabled)
        form.addRow(self.enabled)
        layout.addLayout(form)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(str(T("Enregistrer")))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(str(T("Annuler")))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for button in (self.import_button, self.test_button):
            button.setAutoDefault(False)
        self.trigger.currentIndexChanged.connect(self._trigger_changed)
        if rule is not None:
            self.trigger.setCurrentIndex(self.trigger.findData(rule.trigger.value))
            self.scope.setCurrentIndex(self.scope.findData(rule.scope.value))
            self._add_sound(rule.sound)
            self.sound.setCurrentIndex(self.sound.findData(rule.sound))
        self._trigger_changed()

    def _add_sound(self, sound: SoundRef) -> None:
        if self.sound.findData(sound) < 0:
            self.sound.addItem(sound_title(sound), sound)

    def _trigger_changed(self) -> None:
        self.subject_label.setText(SUBJECT_LABELS[SoundTrigger(self.trigger.currentData())])

    def rule(self) -> SoundRule:
        return SoundRule(
            self.identifier,
            SoundTrigger(self.trigger.currentData()),
            PlayerScope(self.scope.currentData()),
            self.sound.currentData(),
            self.enabled.isChecked(),
        )

    def _preview(self) -> None:
        self.status.clear()
        self.preview_requested.emit(self.sound.currentData())

    def _import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            str(T("Choisir un son")),
            "",
            str(T("Fichiers audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus *.wma)")),
        )
        if not filename:
            return
        try:
            sound = self.library.import_sound(Path(filename))
        except (OSError, ValueError) as error:
            self.status.setText(T("Impossible d’importer le son : {error}", error=str(error)))
            return
        self._add_sound(sound)
        self.sound.setCurrentIndex(self.sound.findData(sound))
        self.status.clear()
