"""Match view separated from connection and diagnostic controls."""

from datetime import UTC, datetime
from sqlite3 import Row

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QVBoxLayout, QWidget

from rocket_lantern.evaluation_button import EvaluationButton
from rocket_lantern.evaluations import Evaluation
from rocket_lantern.i18n import DateText, render
from rocket_lantern.i18n import text as T
from rocket_lantern.match_detail_dialog import MatchDetailDialog, score_label
from rocket_lantern.playlists import playlist_text as playlist_label
from rocket_lantern.result_summary import ResultSummary, outcome_icon
from rocket_lantern.session_detail_dialog import SessionDetailDialog
from rocket_lantern.statistics_panel import StatisticsPanel
from rocket_lantern.storage import MatchStore, Summary
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedComboBox as QComboBox
from rocket_lantern.translated_widgets import TranslatedGroupBox as QGroupBox
from rocket_lantern.translated_widgets import TranslatedItem as QTableWidgetItem
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTable as QTableWidget
from rocket_lantern.translated_widgets import tooltip

OUTCOME_LABELS = {"win": T("Victoire"), "loss": T("Défaite"), "unknown": T("Inconnu")}


class MatchPanel(QWidget):
    """Present current session context and saved results for one player."""

    evaluation_changed = Signal(str, str)

    def __init__(self, player_id: str, player_name: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self.controls = QWidget()
        player_controls = QHBoxLayout(self.controls)
        player_controls.setContentsMargins(0, 0, 0, 0)
        player_controls.setSpacing(8)
        layout.addWidget(self.controls)
        player_controls.addWidget(QLabel(T("Joueur :")))
        self.player = QComboBox()
        self.player.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.player.setMinimumContentsLength(12)
        self.player.addItem(T("Lance un match, puis sélectionne ton joueur"), "")
        if player_id != "":
            self.player.addItem(player_name, player_id)
            self.player.setCurrentIndex(1)
        player_controls.addWidget(self.player, 1)
        self.new_session = QPushButton(T("Nouvelle session"))
        self.new_session.setToolTip(
            T(
                "Remet les compteurs de session à zéro sans effacer l’historique. "
                "Le prochain résultat non encore enregistré rejoindra cette "
                "session, y compris celui du match en cours."
            )
        )
        self.new_session.setEnabled(player_id != "")
        self.session_details = QPushButton(T("Détails de la session"))
        self.session_details.setEnabled(False)
        self.session_details.clicked.connect(self._open_session_detail)
        self.session_details.setToolTip(
            T("Ouvrir la session complète, toutes playlists confondues.")
        )
        player_controls.addWidget(QLabel(T("Période :")))
        self.period = QComboBox()
        self.period.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.period.setMinimumContentsLength(14)
        self.period.addItem(T("Session actuelle"), "current")
        self.period.addItem(T("Tout l’historique"), "all")
        player_controls.addWidget(self.period, 1)
        player_controls.addWidget(QLabel(T("Type de partie :")))
        self.playlist_filter = QComboBox()
        self.playlist_filter.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.playlist_filter.setMinimumContentsLength(14)
        self.playlist_filter.addItem(T("Dernier type joué"), "latest")
        self.playlist_filter.addItem(T("Tous les types"), "all")
        player_controls.addWidget(self.playlist_filter, 1)
        player_controls.addWidget(self.new_session)
        player_controls.addWidget(self.session_details)
        self.current_playlist: int | None = None
        self._store: MatchStore | None = None
        self._player_id = player_id
        self.period.currentIndexChanged.connect(self._filter_changed)
        self.playlist_filter.currentIndexChanged.connect(self._filter_changed)
        self.counters = ResultSummary()
        layout.addWidget(self.counters)
        self._outcome_icons = {"win": outcome_icon("win"), "loss": outcome_icon("loss")}
        self.summary = QGroupBox(T("Statistiques"))
        summary_layout = QVBoxLayout(self.summary)
        self.statistics = StatisticsPanel()
        summary_layout.addWidget(self.statistics)
        layout.addWidget(self.summary)
        self.history_hint = QLabel(T("Matchs · clique sur une ligne pour voir tous les joueurs"))
        layout.addWidget(self.history_hint)
        self.history = QTableWidget(0, 5)
        self.history.setHorizontalHeaderLabels(
            [T("Date"), T("Résultat"), T("Type de partie"), T("Score B–O"), ""]
        )
        assessment_header = self.history.horizontalHeaderItem(4)
        assessment_header.setToolTip(T("Évaluation"))
        assessment_header.setData(Qt.ItemDataRole.AccessibleTextRole, T("Évaluation"))
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        # Include the table cells' 8 px padding on each side of the icon button.
        self.history.horizontalHeader().resizeSection(4, 56)
        for column in (0, 1):
            self.history.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.history.verticalHeader().hide()
        self.history.verticalHeader().setDefaultSectionSize(34)
        self.history.setShowGrid(False)
        self.history.setAlternatingRowColors(True)
        self.history.setStyleSheet(
            "QTableWidget::item { padding: 0 8px; }QHeaderView::section { padding: 5px 8px; }"
        )
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history.cellClicked.connect(self._open_detail)
        self.history.cellActivated.connect(self._open_detail)
        layout.addWidget(self.history, 1)
        self.session = QLabel(T("Partie en cours : en attente de données"))
        self.session.setWordWrap(True)
        layout.addWidget(self.session)
        self.observation = QLabel(T("En attente d’un événement UpdateState."))
        self.observation.setWordWrap(True)
        layout.addWidget(self.observation)
        tooltip(
            self.counters,
            T(
                "Les résultats inconnus sont exclus du taux de victoire. Nouvelle "
                "session automatique après 1 h sans match."
            ),
        )

    def _open_detail(self, row: int, column: int) -> None:
        """Open a read-only match sheet on click or keyboard activation."""
        item = self.history.item(row, 0)
        if self._store is None or item is None or column == 4:
            return
        existing = self.findChild(MatchDetailDialog)
        if existing is not None and existing.isVisible():
            return
        guid = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(guid, str):
            dialog = MatchDetailDialog(self._store, guid, self, self._player_id)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.open()

    def _selected_session_id(self) -> int | None:
        period = self.period.currentData()
        if type(period) is int:
            return period
        if period == "current" and self._store is not None:
            return self._store.current_session(self._player_id, datetime.now(UTC).isoformat())
        return None

    def _open_session_detail(self) -> None:
        session_id = self._selected_session_id()
        if self._store is None or session_id is None:
            return
        dialog = SessionDetailDialog(self._store, self._player_id, session_id, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()

    def observe(self, message: object, reason: str) -> None:
        """Display the playlist even when no player or trackable match is available."""
        self.observation.setText(T(reason))
        if not isinstance(message, dict):
            return
        if message.get("Event") == "MatchDestroyed":
            self.session.setText(T("Partie en cours : en attente de données"))
            return
        if message.get("Event") != "UpdateState":
            return
        data = message.get("Data")
        if not isinstance(data, dict) or not isinstance(data.get("Game"), dict):
            return
        playlist = data["Game"].get("PlaylistId")
        if type(playlist) is not int:
            playlist = None
        self.session.setText(T("Partie en cours : {playlist}", playlist=playlist_label(playlist)))
        if playlist != self.current_playlist:
            self.current_playlist = playlist
            self._filter_changed()

    def _filter_changed(self) -> None:
        if self._store is not None:
            self.refresh(self._store, self._player_id)

    def _update_filters(self, store: MatchStore, player_id: str) -> None:
        sessions = store.sessions(player_id)
        selected_period = self.period.currentData()
        self.period.blockSignals(True)
        self.period.clear()
        self.period.addItem(T("Session actuelle"), "current")
        self.period.addItem(T("Tout l’historique"), "all")
        for session in reversed(sessions):
            started_at = datetime.fromisoformat(session["started_at"])
            date = DateText(started_at)
            self.period.addItem(
                T("Session #{id} du {date}", id=session["id"], date=date), session["id"]
            )
        self.period.setCurrentIndex(max(0, self.period.findData(selected_period)))
        self.period.blockSignals(False)
        selected_playlist = self.playlist_filter.currentData()
        self.playlist_filter.blockSignals(True)
        self.playlist_filter.clear()
        self.playlist_filter.addItem(T("Dernier type joué"), "latest")
        self.playlist_filter.addItem(T("Tous les types"), "all")
        rows = store.filtered_history(player_id, None, None)
        playlists = {row["playlist"] for row in rows}
        if self.current_playlist is not None:
            playlists.add(self.current_playlist)
        for playlist in sorted(playlists, key=lambda value: render(playlist_label(value))):
            self.playlist_filter.addItem(playlist_label(playlist), playlist)
        self.playlist_filter.setCurrentIndex(
            max(0, self.playlist_filter.findData(selected_playlist))
        )
        self.playlist_filter.blockSignals(False)

    def refresh(self, store: MatchStore, player_id: str) -> None:
        """Render stored results using the same playlist labels as live events."""
        self._store = store
        self._player_id = player_id
        self.new_session.setEnabled(player_id != "")
        self._update_filters(store, player_id)
        self.session_details.setEnabled(self._selected_session_id() is not None)
        rows = store.filtered_history(player_id, None, None)
        period = self.period.currentData()
        session_id = None
        if period == "current":
            session_id = store.current_session(player_id, datetime.now(UTC).isoformat())
            if session_id is None:
                session_id = -1
        elif period != "all":
            session_id = period
        playlist = self.playlist_filter.currentData()
        if playlist == "latest":
            playlist = self.current_playlist
            if playlist is None and len(rows) > 0:
                playlist = rows[0]["playlist"]
        filter_playlist = playlist != "all"
        if not filter_playlist:
            playlist = None
        rows = store.filtered_history(player_id, session_id, playlist, filter_playlist)
        period_context = T("historique")
        if period == "current":
            period_context = T("session actuelle")
        if session_id is not None and session_id != -1:
            period_context = T("session #{session_id}", session_id=session_id)
        scope = T("tous les types")
        if filter_playlist:
            scope = playlist_label(playlist)
        self.summary.setTitle(
            T(
                "Synthèse du joueur · {period_context} · {scope}",
                period_context=period_context,
                scope=scope,
            )
        )
        player_name = self.player.currentText()
        if player_id == "":
            player_name = T("aucun joueur sélectionné")
        self.counters.context.setText(
            T(
                "Bilan · {player_name} · {period_context} · {scope}",
                player_name=player_name,
                period_context=period_context,
                scope=scope,
            )
        )
        self.statistics.update_rows(rows)
        self._render_history(rows)

    def _render_history(self, rows: list[Row]) -> None:
        summary = Summary(
            sum(row["outcome"] == "win" for row in rows),
            sum(row["outcome"] == "loss" for row in rows),
            sum(row["outcome"] == "unknown" for row in rows),
        )
        self.counters.set_summary(summary)
        self.history_hint.setText(
            T(
                "Matchs · {displayed} affichés sur {count} · clique sur une ligne "
                "pour voir tous les joueurs",
                displayed=min(100, len(rows)),
                count=len(rows),
            )
        )
        self.history.clearContents()
        self.history.setRowCount(min(100, len(rows)))
        for index, row in enumerate(rows[:100]):
            date = DateText(datetime.fromisoformat(row["ended_at"]))
            values = [date, OUTCOME_LABELS[row["outcome"]], playlist_label(row["playlist"])]
            values.append("")
            for column, value in enumerate(values):
                self.history.setItem(index, column, QTableWidgetItem(value))
            icon = self._outcome_icons.get(row["outcome"])
            if icon is not None:
                self.history.item(index, 1).setIcon(icon)
            self.history.item(index, 0).setData(Qt.ItemDataRole.UserRole, row["match_id"])
            if row["observed_at"] is not None:
                label = score_label(
                    row["blue_score"],
                    row["orange_score"],
                    row["team"],
                    observed=not row["final_observed"],
                )
                label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                self.history.setCellWidget(index, 3, label)
            else:
                self.history.item(index, 3).setText("—")
            button = EvaluationButton(self.history)
            button.set_match(row["match_id"], Evaluation(row["evaluation"]))
            button.selected.connect(self.evaluation_changed)
            self.history.setCellWidget(index, 4, button)

    def update_evaluation(self, guid: str, value: Evaluation) -> None:
        """Refresh the edited badge without resetting history selection or filters."""
        for row in range(self.history.rowCount()):
            item = self.history.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == guid:
                button = self.history.cellWidget(row, 4)
                if isinstance(button, EvaluationButton):
                    button.set_match(guid, value)
