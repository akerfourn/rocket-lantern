"""Sound rules stay editable while automatic playback is disabled."""

from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QSpinBox,
    QStyle,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.i18n import text as T
from rocket_lantern.sound_alerts import (
    MAX_RULES,
    SCOPE_LABELS,
    TRIGGER_LABELS,
    SoundAlertConfig,
    SoundAlertMode,
    SoundRule,
)
from rocket_lantern.sound_library import SoundLibrary, sound_title
from rocket_lantern.sound_rule_dialog import SoundRuleDialog
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedItem as QItem
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget


class SoundAlertSettings(QWidget):
    config_changed = Signal(object)
    preview_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.config = SoundAlertConfig()
        self.library = SoundLibrary(None)
        self.editor: SoundRuleDialog | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem(T("Désactivé"), SoundAlertMode.NEVER.value)
        self.mode.addItem(T("Parties privées uniquement"), SoundAlertMode.PRIVATE.value)
        self.mode.addItem(T("Toutes les parties"), SoundAlertMode.ALL.value)
        form.addRow(QLabel(T("Activation :")), self.mode)
        self.volume = QSpinBox()
        self.volume.setRange(0, 100)
        self.volume.setSuffix(" %")
        self.volume.setKeyboardTracking(False)
        form.addRow(QLabel(T("Volume :")), self.volume)
        layout.addLayout(form)
        self.warning = QLabel(
            T(
                "Certaines alertes peuvent être considérées comme une aide au jeu "
                "et présenter un risque de sanction en ligne."
            )
        )
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #c87518;")
        layout.addWidget(self.warning)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            (T("Actif"), T("Déclencheur"), T("Joueur concerné"), T("Son"))
        )
        self.table.verticalHeader().hide()
        self.table.setMinimumHeight(175)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 45)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        self.add_button = QPushButton(T("Ajouter…"))
        self.edit_button = QPushButton(T("Modifier…"))
        self.remove_button = QPushButton(T("Supprimer"))
        self.test_button = QPushButton(T("Tester"))
        self.test_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        for button in (self.add_button, self.edit_button, self.test_button, self.remove_button):
            button.setAutoDefault(False)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.mode.currentIndexChanged.connect(self._options_changed)
        self.volume.valueChanged.connect(self._options_changed)
        self.table.itemChanged.connect(self._toggle_rule)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(self._edit)
        self.add_button.clicked.connect(self._add)
        self.edit_button.clicked.connect(self._edit)
        self.remove_button.clicked.connect(self._remove)
        self.test_button.clicked.connect(self._preview)
        self.set_config(self.config)

    def set_config(self, config: SoundAlertConfig) -> None:
        selected = self.selected_rule()
        self.config = config
        with QSignalBlocker(self.mode), QSignalBlocker(self.volume), QSignalBlocker(self.table):
            self.mode.setCurrentIndex(self.mode.findData(config.mode.value))
            self.volume.setValue(config.volume)
            self.table.setRowCount(len(config.rules))
            for row, rule in enumerate(config.rules):
                enabled = QTableWidgetItem()
                enabled.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                enabled.setCheckState(
                    Qt.CheckState.Checked if rule.enabled else Qt.CheckState.Unchecked
                )
                enabled.setData(Qt.ItemDataRole.UserRole, rule.id)
                self.table.setItem(row, 0, enabled)
                for column, title in enumerate(
                    (
                        TRIGGER_LABELS[rule.trigger],
                        SCOPE_LABELS[rule.scope],
                        sound_title(rule.sound),
                    ),
                    start=1,
                ):
                    item = QItem(title)
                    item.setToolTip(title)
                    self.table.setItem(row, column, item)
                if selected is not None and rule.id == selected.id:
                    self.table.selectRow(row)
        self.add_button.setEnabled(len(config.rules) < MAX_RULES)
        self._selection_changed()

    def selected_rule(self) -> SoundRule | None:
        row = self.table.currentRow()
        if 0 <= row < len(self.config.rules):
            return self.config.rules[row]
        return None

    def _selection_changed(self) -> None:
        selected = self.selected_rule() is not None
        for button in (self.edit_button, self.remove_button, self.test_button):
            button.setEnabled(selected)

    def _options_changed(self) -> None:
        self.config_changed.emit(
            replace(
                self.config,
                mode=SoundAlertMode(self.mode.currentData()),
                volume=self.volume.value(),
            )
        )

    def _toggle_rule(self, item: QTableWidgetItem) -> None:
        if item.column() != 0 or not 0 <= item.row() < len(self.config.rules):
            return
        rules = list(self.config.rules)
        rules[item.row()] = replace(
            rules[item.row()], enabled=item.checkState() == Qt.CheckState.Checked
        )
        self.config_changed.emit(replace(self.config, rules=tuple(rules)))

    def _add(self) -> None:
        self._open_editor(None)

    def _edit(self) -> None:
        rule = self.selected_rule()
        if rule is not None:
            self._open_editor(rule)

    def _open_editor(self, rule: SoundRule | None) -> None:
        if self.editor is not None:
            self.editor.raise_()
            return
        sounds = tuple(dict.fromkeys(item.sound for item in self.config.rules))
        self.editor = SoundRuleDialog(rule, sounds, self.library, self.window())
        self.editor.preview_requested.connect(self.preview_requested.emit)
        self.editor.accepted.connect(self._save_editor)
        self.editor.finished.connect(self._editor_finished)
        self.editor.open()

    def _save_editor(self) -> None:
        if self.editor is None:
            return
        rule = self.editor.rule()
        rules = list(self.config.rules)
        for index, existing in enumerate(rules):
            if existing.id == rule.id:
                rules[index] = rule
                break
        else:
            rules.append(rule)
        self.config_changed.emit(replace(self.config, rules=tuple(rules)))
        for row, saved in enumerate(self.config.rules):
            if saved.id == rule.id:
                self.table.selectRow(row)
                break

    def _editor_finished(self) -> None:
        if self.editor is not None:
            self.editor.deleteLater()
            self.editor = None

    def _remove(self) -> None:
        rule = self.selected_rule()
        if rule is not None:
            rules = tuple(item for item in self.config.rules if item.id != rule.id)
            self.config_changed.emit(replace(self.config, rules=rules))

    def _preview(self) -> None:
        rule = self.selected_rule()
        if rule is not None:
            self.preview_requested.emit(rule.sound)
