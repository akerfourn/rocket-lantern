"""Match view separated from connection and diagnostic controls."""

from datetime import datetime

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rl_winloose.playlists import playlist_label
from rl_winloose.storage import MatchStore

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
        self.counters = QLabel()
        self.counters.setStyleSheet("font-size: 16px; padding: 10px 0;")
        self.counters.setWordWrap(True)
        layout.addWidget(self.counters)
        self.history = QTableWidget(0, 3)
        self.history.setHorizontalHeaderLabels(["Date", "Résultat", "Type de partie"])
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history.verticalHeader().hide()
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.history)
        hint = QLabel(
            "100 derniers matchs affichés · Compteurs sur tout l’historique du joueur.\n"
            "Un résultat non reçu reste inconnu et ne compte pas dans le taux de victoire."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

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

    def refresh(self, store: MatchStore, player_id: str) -> None:
        """Render stored results using the same playlist labels as live events."""
        summary = store.summary(player_id)
        self.counters.setText(
            f"{summary.wins} victoires    {summary.losses} défaites    "
            f"{summary.win_rate:.1f} % de victoires    {summary.unknown} inconnus"
        )
        rows = store.history(player_id)
        self.history.setRowCount(len(rows))
        for index, row in enumerate(rows):
            date = datetime.fromisoformat(row["ended_at"]).astimezone().strftime("%d/%m/%Y %H:%M")
            values = [date, OUTCOME_LABELS[row["outcome"]], playlist_label(row["playlist"])]
            for column, value in enumerate(values):
                self.history.setItem(index, column, QTableWidgetItem(value))
