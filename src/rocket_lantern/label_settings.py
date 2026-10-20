"""Two-pane category editor with an atomic, explicit apply action."""

import sqlite3
from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QHideEvent, QKeySequence, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QKeySequenceEdit,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStyle,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.global_hotkeys import HotkeyError, HotkeyProblem, validate_hotkeys
from rocket_lantern.i18n import render
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.label_icons import colored_tag, label_icon
from rocket_lantern.labels import Label, LabelList, custom_id
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget
from rocket_lantern.translated_widgets import binding


class LabelSettings(QDialog):
    failed = Signal()
    opened = Signal()
    hidden = Signal()

    def __init__(self, catalog: LabelCatalog, parent: QWidget) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self._groups: dict[str, LabelList] = {}
        self._labels: dict[str, Label] = {}
        self._group_id = ""
        self._label_id = ""
        self._color = "#aab1ba"
        self._loading = False
        self._saving = False
        self._conflict = False
        self._baseline: tuple[tuple[LabelList, ...], tuple[Label, ...]] = ((), ())
        self.setWindowTitle(T("Étiquettes"))
        self.resize(830, 720)
        root = QVBoxLayout(self)
        splitter = QSplitter()
        root.addWidget(splitter, 1)
        self._build_categories(splitter)
        self._build_details(splitter)
        splitter.setSizes([210, 580])
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.apply_button = QPushButton(T("Appliquer"))
        self.apply_button.clicked.connect(self.apply)
        self.close_button = QPushButton(T("Fermer"))
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self._connect_editors()
        catalog.changed.connect(self._catalog_changed)
        binding(self).callbacks.append(self._translate)
        self.reload()

    def _connect_editors(self) -> None:
        self.lists.currentRowChanged.connect(self._select_category)
        self.items.currentCellChanged.connect(self._select_label)
        self.items.itemChanged.connect(self._toggle_label)
        self.list_name.textEdited.connect(self._edited)
        self.label_name.textEdited.connect(self._edited)
        self.list_enabled.toggled.connect(self._edited)
        self.family.currentIndexChanged.connect(self._edited)
        self.symbol.currentIndexChanged.connect(self._edited)
        self.shortcut.keySequenceChanged.connect(self._edited)

    def _build_categories(self, splitter: QSplitter) -> None:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.addWidget(QLabel(T("Catégories")))
        self.lists = QListWidget()
        self.lists.setMinimumWidth(150)
        layout.addWidget(self.lists, 1)
        self.add_list = QPushButton(T("Nouvelle catégorie…"))
        self.add_list.clicked.connect(self._add_list)
        layout.addWidget(self.add_list)
        self.category_up, self.category_down = self._order_buttons(layout, True)
        splitter.addWidget(pane)

    def _build_details(self, splitter: QSplitter) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.general = QGroupBox(T("Catégorie"))
        form = QFormLayout(self.general)
        self.list_name = QLineEdit()
        self.list_name.setMaxLength(80)
        self.list_enabled = QCheckBox(T("Catégorie active"))
        self.family = QComboBox()
        for title, value in (
            (T("Étiquette"), "tag"),
            (T("Drapeau"), "flag"),
            (T("Bouclier"), "shield"),
        ):
            self.family.addItem(title, value)
            icon = colored_tag("tag", "#aab1ba", value)
            self.family.setItemIcon(self.family.count() - 1, icon)
        form.addRow(QLabel(T("Nom :")), self.list_name)
        form.addRow(self.list_enabled)
        form.addRow(QLabel(T("Famille d’icônes :")), self.family)
        layout.addWidget(self.general)
        self._build_label_table(layout)
        self._build_label_fields(layout)
        scroll.setWidget(content)
        splitter.addWidget(scroll)

    def _build_label_table(self, layout: QVBoxLayout) -> None:
        self.items = QTableWidget(0, 3)
        self.items.setHorizontalHeaderLabels([T("Étiquette"), T("Raccourci"), T("Active")])
        self.items.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.items.verticalHeader().hide()
        header = self.items.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.items.setMinimumHeight(150)
        layout.addWidget(self.items, 1)
        line = QHBoxLayout()
        self.add_label = QPushButton(T("Nouvelle étiquette…"))
        self.add_label.clicked.connect(self._add_label)
        line.addWidget(self.add_label)
        line.addStretch()
        self.label_up, self.label_down = self._order_buttons(line, False)
        layout.addLayout(line)

    def _build_label_fields(self, layout: QVBoxLayout) -> None:
        self.label_fields = QGroupBox(T("Étiquette"))
        form = QFormLayout(self.label_fields)
        self.label_name = QLineEdit()
        self.label_name.setMaxLength(80)
        self.symbol = QComboBox()
        for title, value in (
            (T("Sans symbole"), "tag"),
            (T("Tiret"), "not_evaluated"),
            (T("Coche"), "no_suspicion"),
            (T("Point d’interrogation"), "possible"),
            (T("Point d’exclamation"), "strong"),
        ):
            self.symbol.addItem(title, value)
        self.color_button = QPushButton(T("Choisir la couleur…"))
        self.color_button.clicked.connect(self._pick_color)
        self.shortcut = QKeySequenceEdit()
        self.shortcut.setMaximumSequenceLength(1)
        self.shortcut.setClearButtonEnabled(True)
        form.addRow(QLabel(T("Nom :")), self.label_name)
        form.addRow(QLabel(T("Variante intérieure :")), self.symbol)
        form.addRow(QLabel(T("Couleur :")), self.color_button)
        form.addRow(QLabel(T("Raccourci :")), self.shortcut)
        layout.addWidget(self.label_fields)

    def _order_buttons(
        self, layout: QVBoxLayout | QHBoxLayout, categories: bool
    ) -> tuple[QPushButton, QPushButton]:
        row = QHBoxLayout()
        buttons = []
        for delta, title, icon in (
            (-1, T("Monter"), QStyle.StandardPixmap.SP_ArrowUp),
            (1, T("Descendre"), QStyle.StandardPixmap.SP_ArrowDown),
        ):
            button = QPushButton(title)
            button.setIcon(self.style().standardIcon(icon))
            button.clicked.connect(lambda checked=False, step=delta: self._move(categories, step))
            row.addWidget(button)
            buttons.append(button)
        layout.addLayout(row)
        return buttons[0], buttons[1]

    def reload(self) -> None:
        self._groups = {item.id: item for item in self.catalog.lists}
        self._labels = dict(self.catalog.labels)
        self._baseline = (tuple(self._groups.values()), tuple(self._labels.values()))
        self._conflict = False
        self._show_categories()
        self._show_category()
        self._update_state()

    def _show_categories(self) -> None:
        with QSignalBlocker(self.lists):
            self.lists.clear()
            for group in self._groups.values():
                icon = colored_tag("tag", "#aab1ba", group.family)
                item = QListWidgetItem(icon, render(group.title))
                item.setData(Qt.ItemDataRole.UserRole, group.id)
                self.lists.addItem(item)
                if group.id == self._group_id:
                    self.lists.setCurrentItem(item)
            if self.lists.currentRow() < 0:
                self.lists.setCurrentRow(0)
        item = self.lists.currentItem()
        self._group_id = ""
        if item is not None:
            self._group_id = item.data(Qt.ItemDataRole.UserRole)

    def _group_labels(self) -> list[Label]:
        return sorted(
            (item for item in self._labels.values() if item.list_id == self._group_id),
            key=lambda item: (item.position, item.id),
        )

    def _show_category(self) -> None:
        self._loading = True
        group = self._groups.get(self._group_id)
        self.general.setEnabled(group is not None)
        self.add_label.setEnabled(group is not None)
        if group is not None:
            self.list_name.setText(render(group.title))
            self.list_enabled.setChecked(group.enabled)
            self.family.setCurrentIndex(self.family.findData(group.family))
        with QSignalBlocker(self.items):
            self.items.setRowCount(0)
            for label in self._group_labels():
                self._insert_label(label, group)
            if self.items.currentRow() < 0 and self.items.rowCount():
                self.items.setCurrentCell(0, 0)
        self._loading = False
        self._show_label()

    def _insert_label(self, label: Label, group: LabelList) -> None:
        row = self.items.rowCount()
        self.items.insertRow(row)
        name = QTableWidgetItem(label_icon(label, group.family), render(label.title))
        name.setData(Qt.ItemDataRole.UserRole, label.id)
        self.items.setItem(row, 0, name)
        self.items.setItem(row, 1, QTableWidgetItem(label.shortcut))
        active = QTableWidgetItem()
        active.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        active.setCheckState(Qt.CheckState.Checked if label.enabled else Qt.CheckState.Unchecked)
        self.items.setItem(row, 2, active)
        if label.id == self._label_id:
            self.items.setCurrentCell(row, 0)

    def _show_label(self) -> None:
        self._loading = True
        cell = self.items.item(self.items.currentRow(), 0)
        self._label_id = ""
        if cell is not None:
            self._label_id = cell.data(Qt.ItemDataRole.UserRole)
        label = self._labels.get(self._label_id)
        self.label_fields.setEnabled(label is not None)
        if label is not None:
            self.label_name.setText(render(label.title))
            self.symbol.setCurrentIndex(self.symbol.findData(label.symbol))
            self.shortcut.setKeySequence(QKeySequence(label.shortcut))
            self._color = label.color
        else:
            self.label_name.clear()
            self.shortcut.clear()
        self._loading = False
        self._refresh_icons()
        self._update_state()

    def _capture(self) -> None:
        if self._loading:
            return
        group = self._groups.get(self._group_id)
        if group is not None:
            name = self.list_name.text()
            if name == render(group.title):
                name = group.name
            self._groups[group.id] = replace(
                group,
                name=name,
                enabled=self.list_enabled.isChecked(),
                family=self.family.currentData(),
            )
        label = self._labels.get(self._label_id)
        if label is not None:
            name = self.label_name.text()
            if name == render(label.title):
                name = label.name
            self._labels[label.id] = replace(
                label,
                name=name,
                color=self._color,
                symbol=self.symbol.currentData(),
                shortcut=self.shortcut.keySequence().toString(
                    QKeySequence.SequenceFormat.PortableText
                ),
            )

    def _edited(self, *args: object) -> None:
        if self._loading:
            return
        self._capture()
        self._refresh_icons()
        self._update_state()

    def _refresh_icons(self) -> None:
        group = self._groups.get(self._group_id)
        if group is None:
            return
        for row in range(self.lists.count()):
            cell = self.lists.item(row)
            definition = self._groups[cell.data(Qt.ItemDataRole.UserRole)]
            cell.setText(render(definition.title))
            cell.setIcon(colored_tag("tag", "#aab1ba", definition.family))
        with QSignalBlocker(self.items):
            for row in range(self.items.rowCount()):
                cell = self.items.item(row, 0)
                label = self._labels[cell.data(Qt.ItemDataRole.UserRole)]
                cell.setText(render(label.title))
                cell.setIcon(label_icon(label, group.family))
                self.items.item(row, 1).setText(label.shortcut)
        self.color_button.setIcon(
            colored_tag(self.symbol.currentData() or "tag", self._color, group.family)
        )
        for index in range(self.symbol.count()):
            self.symbol.setItemIcon(
                index, colored_tag(self.symbol.itemData(index), self._color, group.family)
            )

    def _select_category(self, row: int) -> None:
        self._capture()
        item = self.lists.item(row)
        if item is None:
            return
        self._group_id = item.data(Qt.ItemDataRole.UserRole)
        self._show_category()

    def _select_label(self, row: int, column: int, previous_row: int, previous_column: int) -> None:
        self._capture()
        self._show_label()

    def _toggle_label(self, cell: QTableWidgetItem) -> None:
        if cell.column() != 2 or self._loading:
            return
        identifier = self.items.item(cell.row(), 0).data(Qt.ItemDataRole.UserRole)
        self._labels[identifier] = replace(
            self._labels[identifier], enabled=cell.checkState() == Qt.CheckState.Checked
        )
        self._update_state()

    def _add_list(self) -> None:
        name, accepted = QInputDialog.getText(
            self, render(T("Nouvelle catégorie")), render(T("Nom :"))
        )
        if not accepted:
            return
        self._capture()
        position = max((item.position for item in self._groups.values()), default=-1) + 1
        group = LabelList(custom_id(), name, position=position)
        self._groups[group.id] = group
        self._group_id = group.id
        self._show_categories()
        self._show_category()

    def _add_label(self) -> None:
        name, accepted = QInputDialog.getText(
            self, render(T("Nouvelle étiquette")), render(T("Nom :"))
        )
        if not accepted:
            return
        self._capture()
        position = max((item.position for item in self._group_labels()), default=-1) + 1
        label = Label(custom_id(), self._group_id, name, position=position)
        self._labels[label.id] = label
        self._label_id = label.id
        self._show_category()

    def _move(self, categories: bool, delta: int) -> None:
        self._capture()
        definitions = list(self._groups.values()) if categories else self._group_labels()
        identifier = self._group_id if categories else self._label_id
        index = next((i for i, item in enumerate(definitions) if item.id == identifier), -1)
        destination = index + delta
        if index < 0 or not 0 <= destination < len(definitions):
            return
        definitions[index], definitions[destination] = definitions[destination], definitions[index]
        if categories:
            self._groups = {
                item.id: replace(item, position=i) for i, item in enumerate(definitions)
            }
            self._show_categories()
        else:
            self._labels.update(
                {item.id: replace(item, position=i) for i, item in enumerate(definitions)}
            )
        self._show_category()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self._color), self, render(T("Couleur de l’étiquette"))
        )
        if color.isValid():
            self._color = color.name()
            self._edited()

    def _dirty(self) -> bool:
        return (tuple(self._groups.values()), tuple(self._labels.values())) != self._baseline

    def _update_state(self) -> None:
        self.apply_button.setEnabled(self._dirty() and not self._conflict)
        row = self.lists.currentRow()
        self.category_up.setEnabled(row > 0)
        self.category_down.setEnabled(0 <= row < self.lists.count() - 1)
        row = self.items.currentRow()
        self.label_up.setEnabled(row > 0)
        self.label_down.setEnabled(0 <= row < self.items.rowCount() - 1)

    def apply(self) -> bool:
        self._capture()
        if self._conflict or self.catalog.repository is None:
            return False
        active = {group.id for group in self._groups.values() if group.enabled}
        shortcuts = tuple(
            item.shortcut
            for item in self._labels.values()
            if item.enabled and item.list_id in active
        )
        try:
            validate_hotkeys(shortcuts, expected_count=None)
            self.catalog.repository.save_catalog(
                tuple(self._groups.values()), tuple(self._labels.values())
            )
        except HotkeyError as error:
            if error.problem == HotkeyProblem.DUPLICATE:
                self.status.setText(T("Chaque évaluation doit avoir un raccourci différent."))
            else:
                self.status.setText(
                    T("Utilise Ctrl, Alt ou Maj avec une lettre, un chiffre ou F1–F24 (sauf F12).")
                )
            return False
        except ValueError:
            self.status.setText(T("Vérifiez les noms, les couleurs et les familles d’icônes."))
            return False
        except sqlite3.Error:
            self.status.setText(T("Impossible d’enregistrer les étiquettes."))
            self.failed.emit()
            return False
        self._saving = True
        try:
            self.catalog.reload()
        finally:
            self._saving = False
        self.reload()
        self.status.setText(T("Étiquettes enregistrées."))
        return True

    def _catalog_changed(self) -> None:
        if self._saving:
            return
        if not self.isVisible() or not self._dirty():
            self.reload()
            return
        self._conflict = True
        self.status.setText(T("La configuration a changé. Fermez puis rouvrez cette fenêtre."))
        self._update_state()

    def _translate(self) -> None:
        self._show_categories()
        self._show_category()

    def showEvent(self, event: QShowEvent) -> None:
        self.reload()
        self.status.clear()
        available = self.screen().availableGeometry()
        self.resize(min(830, available.width() - 30), min(720, available.height() - 60))
        super().showEvent(event)
        self.opened.emit()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.hidden.emit()

    def reject(self) -> None:
        self._capture()
        if self._dirty() and not self._confirm_close():
            return
        self.reload()
        super().reject()

    def _confirm_close(self) -> bool:
        message = QMessageBox(self)
        message.setWindowTitle(render(T("Étiquettes")))
        message.setText(render(T("Enregistrer les modifications avant de fermer ?")))
        save = message.addButton(render(T("Enregistrer")), QMessageBox.ButtonRole.AcceptRole)
        discard = message.addButton(render(T("Ignorer")), QMessageBox.ButtonRole.DestructiveRole)
        message.addButton(render(T("Annuler")), QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() is save:
            return self.apply()
        return message.clickedButton() is discard
