"""Compact player selectors and a multiple-choice event-family menu."""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QAction, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QMenu, QSizePolicy, QStyle, QToolButton, QWidget

from rocket_lantern.event_data import integer
from rocket_lantern.event_deduplication import EventRow
from rocket_lantern.event_filters import FAMILY_LABELS, EventFilterIndex
from rocket_lantern.event_map_panel import player_icon
from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import set_text, tooltip


class FamilyMenu(QMenu):
    """Allow several checkboxes to be changed before dismissing the menu."""

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        action = self.actionAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and self._toggle(action):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and self._toggle(self.activeAction()):
            event.accept()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _toggle(action: QAction | None) -> bool:
        if action is None or not action.isEnabled() or not action.isCheckable():
            return False
        action.trigger()
        return True


class EventFilterControls(QWidget):
    changed = Signal()

    def __init__(
        self,
        index: EventFilterIndex,
        players: Sequence[EventRow],
        participants: Sequence[EventRow],
    ) -> None:
        super().__init__()
        self.index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.actor = QComboBox()
        self.target = QComboBox()
        for combo, label, missing in (
            (self.actor, T("Joueur :"), T("Sans joueur identifié")),
            (self.target, T("Passeur / cible :"), T("Sans cible identifiée")),
        ):
            title = QLabel(label)
            title.setBuddy(combo)
            layout.addWidget(title)
            combo.addItem(T("Tous les joueurs"), None)
            combo.addItem(missing, "unidentified")
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(12)
            combo.setMaximumWidth(220)
            combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            combo.setToolTip(label)
            layout.addWidget(combo)
        self._add_players(players, participants)
        self.families = QToolButton()
        self.families.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        tooltip(self.families, T("Familles d’événements"))
        set_text(
            self.families,
            "accessibleName",
            T("Familles d’événements"),
            self.families.setAccessibleName,
        )
        self.menu = FamilyMenu(self.families)
        self.families.setMenu(self.menu)
        self.family_actions: dict[str, QAction] = {}
        self._add_family_action(T("Tout afficher"), self._show_all)
        self._add_family_action(T("Tout masquer"), self._hide_all)
        self.menu.addSeparator()
        for family, count in index.families.items():
            action = self.menu.addAction("")
            action.setCheckable(True)
            action.setChecked(True)
            set_text(
                self.menu,
                family,
                T("{family} ({count})", family=FAMILY_LABELS[family], count=count),
                action.setText,
            )
            action.toggled.connect(self._changed)
            self.family_actions[family] = action
        self.families.setEnabled(bool(self.family_actions))
        layout.addWidget(self.families)
        self.reset = QToolButton()
        self.reset.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        tooltip(self.reset, T("Réinitialiser les filtres"))
        set_text(
            self.reset,
            "accessibleName",
            T("Réinitialiser les filtres"),
            self.reset.setAccessibleName,
        )
        self.reset.clicked.connect(self.reset_filters)
        layout.addWidget(self.reset)
        layout.addStretch()
        self.actor.currentIndexChanged.connect(self._changed)
        self.target.currentIndexChanged.connect(self._changed)
        self._update_summary()

    def _add_players(self, players: Sequence[EventRow], participants: Sequence[EventRow]) -> None:
        choices = {player["player_id"]: player for player in players}
        for participant in participants:
            identifier = integer(participant["player_id"])
            if identifier is not None:
                choices.setdefault(identifier, participant)
        duplicates: dict[tuple[object, object], int] = {}
        for player in choices.values():
            key = (player["name"], player["team"])
            duplicates[key] = duplicates.get(key, 0) + 1
        for identifier, player in choices.items():
            name = player["name"] or T("Joueur inconnu")
            team = {0: T("Bleue"), 1: T("Orange")}.get(player["team"], T("Équipe inconnue"))
            title = T("{name} · {team}", name=name, team=team)
            if duplicates[(player["name"], player["team"])] > 1:
                title = T(
                    "{name} · {team} · {account}",
                    name=name,
                    team=team,
                    account=player["primary_id"],
                )
            for combo in (self.actor, self.target):
                combo.addItem(title, identifier)
                color = {0: "#56b4e9", 1: "#e69f00"}.get(player["team"], "#a8afb8")
                combo.setItemIcon(combo.count() - 1, player_icon(color))
                combo.setItemData(
                    combo.count() - 1, player["primary_id"] or "", Qt.ItemDataRole.ToolTipRole
                )

    def _add_family_action(self, title: DisplayText, callback: Callable[[], None]) -> None:
        action = self.menu.addAction("")
        set_text(self.menu, str(title), title, action.setText)
        action.triggered.connect(callback)

    def selected_families(self) -> frozenset[str]:
        return frozenset(key for key, action in self.family_actions.items() if action.isChecked())

    def visible_ids(self) -> frozenset[int]:
        return self.index.select(
            self.actor.currentData(), self.target.currentData(), self.selected_families()
        )

    def _update_summary(self) -> None:
        selected = len(self.selected_families())
        total = len(self.family_actions)
        title = T("Familles : {selected}/{total}", selected=selected, total=total)
        if selected == total:
            title = T("Familles : Toutes")
        elif selected == 0:
            title = T("Familles : Aucune")
        set_text(self.families, "text", title, self.families.setText)
        self.reset.setEnabled(
            self.actor.currentData() is not None
            or self.target.currentData() is not None
            or selected != total
        )

    def _changed(self) -> None:
        self._update_summary()
        self.changed.emit()

    def _set_families(self, checked: bool) -> None:
        for action in self.family_actions.values():
            with QSignalBlocker(action):
                action.setChecked(checked)
        self._changed()

    def _show_all(self) -> None:
        self._set_families(True)

    def _hide_all(self) -> None:
        self._set_families(False)

    def reset_filters(self) -> None:
        with QSignalBlocker(self.actor), QSignalBlocker(self.target):
            self.actor.setCurrentIndex(0)
            self.target.setCurrentIndex(0)
        self._show_all()
