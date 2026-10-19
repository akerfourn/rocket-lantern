"""Explicit editors for annotation lists and their labels; no destructive deletion."""

import sqlite3
from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rocket_lantern.i18n import render
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.label_icons import colored_tag
from rocket_lantern.labels import Label, LabelList, custom_id
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import binding


class LabelSettings(QWidget):
    failed = Signal()

    def __init__(self, catalog: LabelCatalog, parent: QWidget) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self._color = "#aab1ba"
        self._displayed_list_name = ""
        self._displayed_label_name = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.lists = QComboBox()
        self.add_list = QPushButton(T("Nouvelle liste…"))
        line = QHBoxLayout()
        line.addWidget(self.lists, 1)
        line.addWidget(self.add_list)
        root.addLayout(line)
        self.list_name = QLineEdit()
        self.list_name.setMaxLength(80)
        self.list_enabled = QCheckBox(T("Liste active"))
        self.list_order = self._order_field()
        self.save_list = QPushButton(T("Enregistrer la liste"))
        group = QGroupBox(T("Liste"))
        form = QFormLayout(group)
        form.addRow(QLabel(T("Nom :")), self.list_name)
        form.addRow(self.list_enabled)
        form.addRow(QLabel(T("Ordre :")), self.list_order)
        form.addRow(self.save_list)
        root.addWidget(group)
        self.items = QComboBox()
        self.add_label = QPushButton(T("Nouvelle étiquette…"))
        line = QHBoxLayout()
        line.addWidget(self.items, 1)
        line.addWidget(self.add_label)
        root.addLayout(line)
        self.label_fields = QGroupBox(T("Étiquette"))
        form = QFormLayout(self.label_fields)
        self.label_name = QLineEdit()
        self.label_name.setMaxLength(80)
        self.label_enabled = QCheckBox(T("Étiquette active"))
        self.color_button = QPushButton(T("Choisir la couleur…"))
        self.symbol = QComboBox()
        for title, value in (
            (T("Étiquette"), "tag"),
            (T("Tiret"), "not_evaluated"),
            (T("Coche"), "no_suspicion"),
            (T("Point d’interrogation"), "possible"),
            (T("Point d’exclamation"), "strong"),
        ):
            self.symbol.addItem(title, value)
        self.label_order = self._order_field()
        self.save_label = QPushButton(T("Enregistrer l’étiquette"))
        form.addRow(QLabel(T("Nom :")), self.label_name)
        form.addRow(self.label_enabled)
        form.addRow(QLabel(T("Symbole :")), self.symbol)
        form.addRow(self.color_button)
        form.addRow(QLabel(T("Ordre :")), self.label_order)
        form.addRow(self.save_label)
        root.addWidget(self.label_fields)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.lists.currentIndexChanged.connect(self._show_list)
        self.items.currentIndexChanged.connect(self._show_label)
        self.add_list.clicked.connect(self._add_list)
        self.add_label.clicked.connect(self._add_label)
        self.save_list.clicked.connect(self._save_list)
        self.save_label.clicked.connect(self._save_label)
        self.color_button.clicked.connect(self._pick_color)
        self.symbol.currentIndexChanged.connect(self._preview_color)
        catalog.changed.connect(self.reload)
        binding(self).callbacks.append(self._translate_names)
        self.reload()

    @staticmethod
    def _order_field() -> QSpinBox:
        field = QSpinBox()
        field.setRange(0, 9999)
        return field

    def reload(self) -> None:
        selected = self.lists.currentData()
        with QSignalBlocker(self.lists):
            self.lists.clear()
            for item in self.catalog.lists:
                self.lists.addItem(item.title, item.id)
            self.lists.setCurrentIndex(max(0, self.lists.findData(selected)))
        self._show_list()

    def _show_list(self) -> None:
        group = next(
            (item for item in self.catalog.lists if item.id == self.lists.currentData()), None
        )
        if group is None:
            return
        self.list_name.setText(render(group.title))
        self._displayed_list_name = self.list_name.text()
        self.list_enabled.setChecked(group.enabled)
        self.list_order.setValue(group.position)
        selected = self.items.currentData()
        with QSignalBlocker(self.items):
            self.items.clear()
            for item in self.catalog.items(group.id):
                self.items.addItem(item.title, item.id)
            self.items.setCurrentIndex(max(0, self.items.findData(selected)))
        self._show_label()

    def _show_label(self) -> None:
        item = self.catalog.labels.get(self.items.currentData())
        self.label_fields.setEnabled(item is not None)
        if item is None:
            self.label_name.clear()
            return
        self.label_name.setText(render(item.title))
        self._displayed_label_name = self.label_name.text()
        self.label_enabled.setChecked(item.enabled)
        self.label_order.setValue(item.position)
        self._color = item.color
        self.symbol.setCurrentIndex(max(0, self.symbol.findData(item.symbol)))
        self._preview_color()

    def _preview_color(self) -> None:
        self.color_button.setIcon(colored_tag(self.symbol.currentData() or "tag", self._color))

    def _translate_names(self) -> None:
        group = next(
            (item for item in self.catalog.lists if item.id == self.lists.currentData()), None
        )
        if group is not None and self.list_name.text() == self._displayed_list_name:
            self.list_name.setText(render(group.title))
            self._displayed_list_name = self.list_name.text()
        item = self.catalog.labels.get(self.items.currentData())
        if item is not None and self.label_name.text() == self._displayed_label_name:
            self.label_name.setText(render(item.title))
            self._displayed_label_name = self.label_name.text()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self._color), self, render(T("Couleur de l’étiquette"))
        )
        if color.isValid():
            self._color = color.name()
            self._preview_color()

    def _add_list(self) -> None:
        name, accepted = QInputDialog.getText(self, render(T("Nouvelle liste")), render(T("Nom :")))
        if accepted:
            item = LabelList(custom_id(), name, position=len(self.catalog.lists))
            if self._write_list(item):
                self.lists.setCurrentIndex(self.lists.findData(item.id))

    def _add_label(self) -> None:
        name, accepted = QInputDialog.getText(
            self, render(T("Nouvelle étiquette")), render(T("Nom :"))
        )
        if accepted:
            group = self.lists.currentData()
            item = Label(custom_id(), group, name, position=len(self.catalog.items(group)))
            if self._write_label(item):
                self.items.setCurrentIndex(self.items.findData(item.id))

    def _save_list(self) -> None:
        item = next(group for group in self.catalog.lists if group.id == self.lists.currentData())
        name = self.list_name.text()
        if name == render(item.title):
            name = item.name
        self._write_list(
            replace(
                item,
                name=name,
                enabled=self.list_enabled.isChecked(),
                position=self.list_order.value(),
            )
        )

    def _save_label(self) -> None:
        item = self.catalog.labels.get(self.items.currentData())
        if item is None:
            return
        name = self.label_name.text()
        if name == render(item.title):
            name = item.name
        self._write_label(
            replace(
                item,
                name=name,
                color=self._color,
                symbol=self.symbol.currentData(),
                enabled=self.label_enabled.isChecked(),
                position=self.label_order.value(),
            )
        )

    def _write_list(self, item: LabelList) -> bool:
        if self.catalog.repository is None:
            return False
        try:
            self.catalog.repository.save_list(item)
        except ValueError:
            self.status.setText(T("Le nom doit contenir entre 1 et 80 caractères."))
            return False
        except sqlite3.Error:
            self.failed.emit()
            return False
        self.catalog.reload()
        self.status.setText(T("Liste enregistrée."))
        return True

    def _write_label(self, item: Label) -> bool:
        if self.catalog.repository is None:
            return False
        try:
            self.catalog.repository.save_label(item)
        except ValueError:
            self.status.setText(T("Vérifiez le nom et la couleur de l’étiquette."))
            return False
        except sqlite3.Error:
            self.failed.emit()
            return False
        self.catalog.reload()
        self.status.setText(T("Étiquette enregistrée."))
        return True
