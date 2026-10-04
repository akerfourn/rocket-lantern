"""Match view separated from connection and diagnostic controls."""

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rl_winloose.match_detail_dialog import MatchDetailDialog, score_label
from rl_winloose.playlists import playlist_label
from rl_winloose.storage import MatchStore, Summary

OUTCOME_LABELS = {"win": "Victoire", "loss": "Défaite", "unknown": "Inconnu"}


class MatchPanel(QWidget):
    """Present current session context and saved results for one player."""

    def __init__(self, player_id: str, player_name: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.session = QLabel("Partie en cours : en attente de données")
        self.session.setWordWrap(True)
        layout.addWidget(self.session)
        self.observation = QLabel("En attente d’un événement UpdateState.")
        self.observation.setWordWrap(True)
        layout.addWidget(self.observation)
        self.player = QComboBox()
        self.player.addItem("Lance un match, puis sélectionne ton joueur", "")
        if player_id != "":
            self.player.addItem(player_name, player_id)
            self.player.setCurrentIndex(1)
        layout.addWidget(self.player)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Période :"))
        self.period = QComboBox()
        self.period.addItem("Session actuelle", "current")
        self.period.addItem("Tout l’historique", "all")
        filters.addWidget(self.period)
        filters.addWidget(QLabel("Type de partie :"))
        self.playlist_filter = QComboBox()
        self.playlist_filter.addItem("Dernier type joué", "latest")
        self.playlist_filter.addItem("Tout", "all")
        filters.addWidget(self.playlist_filter)
        layout.addLayout(filters)
        self.current_playlist: int | None = None
        self._store: MatchStore | None = None
        self._player_id = player_id
        self.period.currentIndexChanged.connect(self._filter_changed)
        self.playlist_filter.currentIndexChanged.connect(self._filter_changed)
        self.counters = QLabel()
        self.counters.setStyleSheet("font-size: 16px; padding: 10px 0;")
        self.counters.setWordWrap(True)
        layout.addWidget(self.counters)
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["Date", "Résultat", "Type de partie", "Score B–O"])
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history.verticalHeader().hide()
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.cellDoubleClicked.connect(self._open_detail)
        layout.addWidget(self.history)
        hint = QLabel(
            "100 derniers matchs du filtre affichés · Nouvelle session après 1 h sans match.\n"
            "Un résultat non reçu reste inconnu et ne compte pas dans le taux de victoire."
            "\nDouble-clique sur un match pour ses statistiques et événements."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _open_detail(self, row: int, column: int) -> None:
        """Open the selected persisted match; a double click never changes data."""
        item = self.history.item(row, 0)
        if self._store is None or item is None:
            return
        guid = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(guid, str):
            dialog = MatchDetailDialog(self._store, guid, self, self._player_id)
            dialog.exec()

    def observe(self, message: object, reason: str) -> None:
        """Display the playlist even when no player or trackable match is available."""
        self.observation.setText(reason)
        if not isinstance(message, dict):
            return
        if message.get("Event") == "MatchDestroyed":
            self.session.setText("Partie en cours : en attente de données")
            return
        if message.get("Event") != "UpdateState":
            return
        data = message.get("Data")
        if not isinstance(data, dict) or not isinstance(data.get("Game"), dict):
            return
        playlist = data["Game"].get("PlaylistId")
        if type(playlist) is not int:
            playlist = None
        self.session.setText(f"Partie en cours : {playlist_label(playlist)}")
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
        self.period.addItem("Session actuelle", "current")
        self.period.addItem("Tout l’historique", "all")
        for start in reversed(sessions):
            date = datetime.fromisoformat(start).astimezone().strftime("%d/%m/%Y %H:%M")
            self.period.addItem(f"Session du {date}", start)
        self.period.setCurrentIndex(max(0, self.period.findData(selected_period)))
        self.period.blockSignals(False)
        selected_playlist = self.playlist_filter.currentData()
        self.playlist_filter.blockSignals(True)
        self.playlist_filter.clear()
        self.playlist_filter.addItem("Dernier type joué", "latest")
        self.playlist_filter.addItem("Tout", "all")
        rows = store.filtered_history(player_id, None, None)
        playlists = {row["playlist"] for row in rows}
        if self.current_playlist is not None:
            playlists.add(self.current_playlist)
        for playlist in sorted(playlists, key=playlist_label):
            self.playlist_filter.addItem(playlist_label(playlist), playlist)
        self.playlist_filter.setCurrentIndex(
            max(0, self.playlist_filter.findData(selected_playlist))
        )
        self.playlist_filter.blockSignals(False)

    def refresh(self, store: MatchStore, player_id: str) -> None:
        """Render stored results using the same playlist labels as live events."""
        self._store = store
        self._player_id = player_id
        self._update_filters(store, player_id)
        rows = store.filtered_history(player_id, None, None)
        period = self.period.currentData()
        session_start = None
        if period == "current":
            now = datetime.now(UTC)
            session_start = now.isoformat()
            if len(rows) > 0:
                latest = datetime.fromisoformat(rows[0]["ended_at"])
                if now - latest < timedelta(hours=1):
                    session_start = store.sessions(player_id)[-1]
        elif period != "all":
            session_start = period
        playlist = self.playlist_filter.currentData()
        if playlist == "latest":
            playlist = self.current_playlist
            if playlist is None and len(rows) > 0:
                playlist = rows[0]["playlist"]
        filter_playlist = playlist != "all"
        if not filter_playlist:
            playlist = None
        rows = store.filtered_history(player_id, session_start, playlist, filter_playlist)
        summary = Summary(
            sum(row["outcome"] == "win" for row in rows),
            sum(row["outcome"] == "loss" for row in rows),
            sum(row["outcome"] == "unknown" for row in rows),
        )
        balance = summary.wins - summary.losses
        balance_label = str(balance)
        if balance > 0:
            balance_label = f"+{balance}"
        self.counters.setText(
            f"{summary.wins} victoires    {summary.losses} défaites ({balance_label})    "
            f"{summary.win_rate:.1f} % de victoires    {summary.unknown} inconnus"
        )
        rows = rows[:100]
        self.history.setRowCount(len(rows))
        for index, row in enumerate(rows):
            date = datetime.fromisoformat(row["ended_at"]).astimezone().strftime("%d/%m/%Y %H:%M")
            values = [date, OUTCOME_LABELS[row["outcome"]], playlist_label(row["playlist"])]
            detail = store.detail(row["match_id"])
            score = "—"
            if (
                detail is not None
                and detail["blue_score"] is not None
                and detail["orange_score"] is not None
            ):
                score = f"{detail['blue_score']}–{detail['orange_score']}"
                if not detail["final_observed"]:
                    score += " (observé)"
            values.append(score)
            for column, value in enumerate(values):
                self.history.setItem(index, column, QTableWidgetItem(value))
            self.history.item(index, 0).setData(Qt.ItemDataRole.UserRole, row["match_id"])
            if detail is not None:
                team = store.player_team(row["match_id"], player_id)
                label = score_label(detail["blue_score"], detail["orange_score"], team)
                if not detail["final_observed"]:
                    label.setText(label.text() + " (observé)")
                self.history.setCellWidget(index, 3, label)
