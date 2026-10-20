"""Search locally observed players and edit bookmarks without changing the tracked account."""

import sqlite3
from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QVBoxLayout

from rocket_lantern.favorite_player_button import FavoritePlayerButton
from rocket_lantern.i18n import text as T
from rocket_lantern.player_favorites import PlayerFavorites
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedDialog as QDialog
from rocket_lantern.translated_widgets import TranslatedItem as QTableWidgetItem
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget
from rocket_lantern.translated_widgets import set_text


class PlayerFavoritesDialog(QDialog):
    failed = Signal()

    def __init__(self, directory: PlayerFavorites, parent: QDialog) -> None:
        super().__init__(parent)
        self.directory = directory
        self.setWindowTitle(T("Joueurs favoris"))
        self.resize(680, 430)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        set_text(
            self.search, "placeholder", T("Rechercher un joueur…"), self.search.setPlaceholderText
        )
        set_text(
            self.search, "accessibleName", T("Rechercher un joueur…"), self.search.setAccessibleName
        )
        layout.addWidget(self.search)
        self.players = QTableWidget(0, 3)
        self.players.setHorizontalHeaderLabels([T("Favoris"), T("Joueur"), T("Identifiant")])
        self.players.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.players.horizontalHeader().resizeSection(0, 64)
        self.players.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.players.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.players.verticalHeader().hide()
        self.players.verticalHeader().setDefaultSectionSize(32)
        self.players.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.players.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.players.setAlternatingRowColors(True)
        self.players.setShowGrid(False)
        layout.addWidget(self.players)
        self.empty = QLabel(T("Aucun joueur correspondant."))
        layout.addWidget(self.empty)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        self.close_button = QPushButton(T("Fermer"))
        self.close_button.clicked.connect(self.close)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)
        self.stars: dict[str, FavoritePlayerButton] = {}
        self.search.textChanged.connect(self._filter)
        directory.changed.connect(self._sync_stars)

    def open(self) -> None:
        if self.isVisible():
            self.raise_()
            return
        self.status.setText("")
        self.players.setRowCount(0)
        self.stars.clear()
        for player in self.directory.players():
            row = self.players.rowCount()
            self.players.insertRow(row)
            star = FavoritePlayerButton()
            star.set_player(
                player.primary_id, player.name, player.primary_id in self.directory.favorites
            )
            star.clicked.connect(partial(self._toggle, player.primary_id))
            self.stars[player.primary_id] = star
            self.players.setCellWidget(row, 0, star)
            self.players.setItem(row, 1, QTableWidgetItem(player.name))
            self.players.setItem(row, 2, QTableWidgetItem(player.primary_id))
        self._filter()
        super().open()
        self.search.setFocus(Qt.FocusReason.OtherFocusReason)

    def _filter(self) -> None:
        query = self.search.text().strip().casefold()
        visible = False
        for row in range(self.players.rowCount()):
            name = self.players.item(row, 1).text()
            primary_id = self.players.item(row, 2).text()
            matches = query in name.casefold() or query in primary_id.casefold()
            self.players.setRowHidden(row, not matches)
            visible = visible or matches
        self.empty.setVisible(not visible)

    def _sync_stars(self) -> None:
        for primary_id, star in self.stars.items():
            star.set_player(
                primary_id, self.directory.known[primary_id], primary_id in self.directory.favorites
            )

    def _toggle(self, primary_id: str) -> None:
        try:
            self.directory.set_favorite(
                primary_id, self.directory.known[primary_id], self.stars[primary_id].isChecked()
            )
        except sqlite3.Error:
            self._sync_stars()
            self.status.setText(T("Impossible d’enregistrer les favoris."))
            self.failed.emit()
            return
        self.status.setText("")
