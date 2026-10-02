"""Compact Qt interface for a single player's saved match history."""

import logging
import sqlite3
from datetime import UTC, datetime

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from rl_winloose.client import StatsClient
from rl_winloose.log_panel import LogPanel
from rl_winloose.match_panel import MatchPanel
from rl_winloose.playlists import playlist_label
from rl_winloose.storage import MatchStore
from rl_winloose.tracker import MatchResult, MatchTracker

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Coordinate live observations, local persistence and widget updates."""

    def __init__(self, store: MatchStore) -> None:
        super().__init__()
        self.store = store
        self.tracker = MatchTracker(store.setting("player_id"))
        self.selected_name = store.setting("player_name")
        self.player_options: tuple[tuple[str, str], ...] = ()
        self.observation_status = ""
        self.client = StatsClient(self)
        self.setWindowTitle("RL Win/Loss")
        self.resize(850, 600)
        self._build_interface()
        self.client.message_received.connect(self._receive)
        self.client.status_changed.connect(self.status.setText)
        self.client.connection_lost.connect(self._connection_lost)
        self.client.diagnostic.connect(self.logs.append_entry)
        self.logs.append_entry("Application", "Prête ; connexion à la Stats API officielle locale.")
        self._refresh()

    def _build_interface(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        title = QLabel("Rocket League · Win/Loss")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)
        self.status = QLabel("Prêt à se connecter")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addLayout(self._connection_controls())
        self.tabs = QTabWidget()
        self.matches = MatchPanel(self.tracker.player_id, self.selected_name)
        self.matches.player.currentIndexChanged.connect(self._select_player)
        self.logs = LogPanel()
        self.tabs.addTab(self.matches, "Matchs")
        self.tabs.addTab(self.logs, "Logs")
        layout.addWidget(self.tabs)
        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.setCentralWidget(container)

    def _connection_controls(self) -> QHBoxLayout:
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Port local :"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        saved_port = self.store.setting("port")
        port = 49124
        if saved_port.isdecimal() and 1 <= int(saved_port) <= 65535:
            port = int(saved_port)
        self.port.setValue(port)
        controls.addWidget(self.port)
        reconnect = QPushButton("Reconnecter")
        reconnect.clicked.connect(self.start)
        controls.addWidget(reconnect)
        controls.addStretch()
        return controls

    def start(self) -> None:
        """Start or restart observation using the user-selected local port."""
        self._connection_lost()
        try:
            self.store.set_setting("port", str(self.port.value()))
        except sqlite3.Error:
            self._storage_error()
        self.client.start(self.port.value())

    def _receive(self, payload: str) -> None:
        observed_at = datetime.now(UTC)
        try:
            message = self.logs.record_payload(payload, observed_at)
            results = self.tracker.handle(message, observed_at.isoformat())
        except (ValueError, RecursionError) as error:
            LOGGER.warning("Stats API message rejected: %s", error)
            self.notice.setText("Message API invalide ignoré ; le suivi continue.")
            self.logs.append_entry("Rejet", str(error), observed_at)
            return
        self.matches.observe(message, self.tracker.status)
        self._log_observation()
        self._update_players()
        self._save_results(results)

    def _log_observation(self) -> None:
        if self.tracker.status != self.observation_status:
            self.observation_status = self.tracker.status
            self.logs.append_entry("Suivi", self.observation_status)

    def _update_players(self) -> None:
        options = tuple((player.primary_id, player.name) for player in self.tracker.players)
        if options == self.player_options:
            return
        self.player_options = options
        selector = self.matches.player
        selector.blockSignals(True)
        selector.clear()
        selector.addItem("Sélectionne ton joueur dans le match", "")
        for player in self.tracker.players:
            selector.addItem(player.name, player.primary_id)
        index = selector.findData(self.tracker.player_id)
        if index < 0 and self.tracker.player_id != "":
            selector.addItem(self.selected_name, self.tracker.player_id)
            index = selector.count() - 1
        selector.setCurrentIndex(max(0, index))
        selector.blockSignals(False)

    def _select_player(self, index: int) -> None:
        player_id = self.matches.player.itemData(index)
        if not isinstance(player_id, str) or player_id == self.tracker.player_id:
            return
        self._save_results(self.tracker.interrupt(datetime.now(UTC).isoformat()))
        self.tracker.select_player(player_id)
        self.selected_name = self.matches.player.currentText()
        self.logs.append_entry("Suivi", "Sélection du joueur modifiée.")
        try:
            self.store.set_setting("player_id", player_id)
            self.store.set_setting("player_name", self.selected_name)
            self._refresh()
        except sqlite3.Error:
            self._storage_error()

    def _connection_lost(self) -> None:
        self._save_results(self.tracker.interrupt(datetime.now(UTC).isoformat()))
        self.matches.session.setText("Partie en cours : en attente de données")
        self.matches.observation.setText(self.tracker.status)
        self._log_observation()

    def _save_results(self, results: list[MatchResult]) -> None:
        if len(results) == 0:
            return
        try:
            for result in results:
                self.store.save(result)
                self.logs.append_entry(
                    "Résultat", f"{result.outcome} • {playlist_label(result.playlist)}"
                )
            self._refresh()
        except sqlite3.Error:
            self._storage_error()

    def _refresh(self) -> None:
        self.matches.refresh(self.store, self.tracker.player_id)

    def _storage_error(self) -> None:
        LOGGER.error("Local database operation failed")
        self.notice.setText(
            "Erreur SQLite : certaines données n’ont pas pu être lues ou enregistrées."
        )
        self.logs.append_entry("SQLite", self.notice.text())

    def closeEvent(self, event: QCloseEvent) -> None:
        """Save an unfinished observation and stop networking before closing."""
        self.client.stop()
        self._connection_lost()
        super().closeEvent(event)
