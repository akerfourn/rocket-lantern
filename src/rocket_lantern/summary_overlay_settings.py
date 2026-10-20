"""Live content choices for the W/L overlay, using stable category identifiers."""

from dataclasses import replace
from functools import partial

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.summary_overlay_content import SummaryOverlayContent
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel


class SummaryOverlaySettings(QGroupBox):
    changed = Signal()

    def __init__(self, catalog: LabelCatalog) -> None:
        super().__init__(T("Contenu"))
        self.catalog = catalog
        self.content = SummaryOverlayContent()
        layout = QVBoxLayout(self)
        counters = QHBoxLayout()
        self.wins = QCheckBox(T("Victoires"))
        self.losses = QCheckBox(T("Défaites"))
        self.delta = QCheckBox(T("Delta"))
        for checkbox in (self.wins, self.losses, self.delta):
            checkbox.setChecked(True)
            counters.addWidget(checkbox)
            checkbox.toggled.connect(self._counters_changed)
        counters.addStretch()
        layout.addLayout(counters)
        layout.addWidget(QLabel(T("Étiquettes")))
        self._categories = QVBoxLayout()
        layout.addLayout(self._categories)
        self.category_checks: dict[str, QCheckBox] = {}
        self.empty_hint = QLabel(T("Sélectionnez au moins un élément à afficher."))
        self.empty_hint.setWordWrap(True)
        layout.addWidget(self.empty_hint)
        self._sync_categories()
        catalog.changed.connect(self._sync_categories)

    def set_content(self, content: SummaryOverlayContent) -> None:
        self.content = content
        for checkbox, checked in (
            (self.wins, content.wins),
            (self.losses, content.losses),
            (self.delta, content.delta),
        ):
            with QSignalBlocker(checkbox):
                checkbox.setChecked(checked)
        for key, checkbox in self.category_checks.items():
            with QSignalBlocker(checkbox):
                checkbox.setChecked(key in content.label_lists)
        self.empty_hint.setVisible(not content.has_content(self.catalog))

    def _sync_categories(self) -> None:
        for checkbox in self.category_checks.values():
            self._categories.removeWidget(checkbox)
            checkbox.hide()
            checkbox.deleteLater()
        self.category_checks.clear()
        for category in self.catalog.lists:
            checkbox = QCheckBox(category.title)
            checkbox.setEnabled(category.enabled)
            checkbox.setChecked(category.id in self.content.label_lists)
            checkbox.toggled.connect(partial(self._category_changed, category.id))
            self.category_checks[category.id] = checkbox
            self._categories.addWidget(checkbox)
        self.empty_hint.setVisible(not self.content.has_content(self.catalog))

    def _counters_changed(self) -> None:
        self.set_content(
            replace(
                self.content,
                wins=self.wins.isChecked(),
                losses=self.losses.isChecked(),
                delta=self.delta.isChecked(),
            )
        )
        self.changed.emit()

    def _category_changed(self, key: str, checked: bool) -> None:
        selected = list(self.content.label_lists)
        if checked and key not in selected:
            selected.append(key)
        elif not checked and key in selected:
            selected.remove(key)
        self.set_content(replace(self.content, label_lists=tuple(selected)))
        self.changed.emit()
