"""Compact Qt interface for a single player's saved match history."""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from rocket_lantern.branding import APP_NAME, application_icon
from rocket_lantern.client import StatsClient
from rocket_lantern.evaluation_controller import EvaluationController
from rocket_lantern.hotkey_controller import HotkeyController
from rocket_lantern.i18n import language_manager
from rocket_lantern.i18n import text as T
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.log_panel import LogPanel
from rocket_lantern.match_data import MatchCollector, MatchSnapshot
from rocket_lantern.match_panel import MatchPanel
from rocket_lantern.onboarding_controller import OnboardingController
from rocket_lantern.playlists import playlist_label
from rocket_lantern.settings_panel import SettingsPanel
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult, MatchTracker
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTabWidget as QTabWidget
from rocket_lantern.update_controller import UpdateController

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Coordinate live observations, local persistence and widget updates."""

    def __init__(self, store: MatchStore) -> None:
        super().__init__()
        self.store = store
        self.languages = language_manager()
        saved_language = store.setting("language")
        if saved_language in ("fr", "en"):
            self.languages.set_language(saved_language)
        self.tracker = MatchTracker(store.setting("player_id"))
        self.collector = MatchCollector()
        self._detail_signatures: dict[str, tuple[object, ...]] = {}
        self.selected_name = store.setting("player_name")
        self.player_options: tuple[tuple[str, str], ...] = ()
        self.observation_status = ""
        self.client = StatsClient(self)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(application_icon())
        self.resize(1050, 800)
        self._build_interface()
        self.onboarding = OnboardingController(store, self.settings, self)
        self.onboarding.failed.connect(self._storage_error)
        self.onboarding.reconnect_requested.connect(self.start)
        self.evaluations = EvaluationController(store, self.matches, self)
        self.evaluations.failed.connect(self._storage_error)
        self.hotkeys = HotkeyController(self.settings, store)
        self.hotkeys.failed.connect(self._storage_error)
        self.hotkeys.registration_failed.connect(self._hotkey_error)
        self.hotkeys.activated.connect(self.evaluations.vote_current)
        if self.hotkeys.problem is not None:
            self._hotkey_error()
        self.client.message_received.connect(self._receive)
        self.client.status_changed.connect(self._update_status)
        self.languages.changed.connect(self._sync_language)
        self.client.connection_lost.connect(self._connection_lost)
        self.client.diagnostic.connect(self.logs.append_entry)
        self.logs.append_entry(
            T("Application"), T("Prête ; connexion à la Stats API officielle locale.")
        )
        self._refresh()

    def _build_interface(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        header = QHBoxLayout()
        logo = QLabel()
        logo.setObjectName("application_logo")
        logo.setPixmap(self.windowIcon().pixmap(40, 40))
        logo.setFixedSize(40, 40)
        logo.setAccessibleName(f"Logo {APP_NAME}")
        header.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch()
        self.settings_button = QPushButton(T("Paramètres"))
        self.settings_button.setIcon(QIcon(str(Path(__file__).parent / "assets/settings.svg")))
        self.settings_button.clicked.connect(self._show_settings)
        header.addWidget(self.settings_button)
        layout.addLayout(header)
        self.status = QLabel(T("Prêt à se connecter"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        self.matches = MatchPanel(self.tracker.player_id, self.selected_name)
        self.matches.player.currentIndexChanged.connect(self._select_player)
        self.matches.new_session.clicked.connect(self._start_session)
        layout.addWidget(self.matches.controls)
        layout.addWidget(self.matches.counters)
        self.live = LiveMatchPanel(self.tracker.player_id, self.store.setting("boost_side"))
        self.live.boost_side_changed.connect(self._save_boost_side)
        self.logs = LogPanel()
        self.tabs.addTab(self.matches, T("Matchs"))
        self.tabs.addTab(self.live, T("Partie en cours"))
        self.tabs.addTab(self.logs, T("Logs"))
        if self.store.setting("default_tab") == "live":
            self.tabs.setCurrentIndex(1)
        layout.addWidget(self.tabs)
        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.setCentralWidget(container)
        self._build_settings()
        self.updates = UpdateController(self, self.settings, self.store)
        header.insertWidget(2, self.updates.button)

    def _build_settings(self) -> SettingsPanel:
        saved_port = self.store.setting("port")
        port = 49124
        if saved_port.isdecimal() and 1 <= int(saved_port) <= 65535:
            port = int(saved_port)
        self.settings = SettingsPanel(
            port, self.languages.language, self.store.setting("default_tab"), self
        )
        self.port = self.settings.port
        self.language = self.settings.language
        self.settings.reconnect.clicked.connect(self.start)
        self.port.valueChanged.connect(self._save_port)
        self.settings.default_tab.currentIndexChanged.connect(self._save_default_tab)
        self.language.currentIndexChanged.connect(self._change_language)
        saved_rate = self.store.setting("packet_send_rate")
        if saved_rate.isdecimal() and 1 <= int(saved_rate) <= 120:
            self.settings.game_installations.packet_rate.setValue(int(saved_rate))
        self.settings.game_installations.packet_rate.valueChanged.connect(
            self._save_packet_send_rate
        )
        return self.settings

    def _save_packet_send_rate(self, value: int) -> None:
        try:
            self.store.set_setting("packet_send_rate", str(value))
        except sqlite3.Error:
            self._storage_error()

    def _show_settings(self) -> None:
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def _save_port(self, value: int) -> None:
        try:
            self.store.set_setting("port", str(value))
        except sqlite3.Error:
            self._storage_error()

    def _save_default_tab(self, index: int) -> None:
        try:
            self.store.set_setting("default_tab", self.settings.default_tab.itemData(index))
        except sqlite3.Error:
            self._storage_error()

    def _update_status(self, message: str) -> None:
        self.status.setText(self.client.current_status)

    def _sync_language(self, language: str) -> None:
        with QSignalBlocker(self.language):
            self.language.setCurrentIndex(self.language.findData(language))

    def _change_language(self, index: int) -> None:
        language = self.language.itemData(index)
        self.languages.set_language(language)
        try:
            self.store.set_setting("language", language)
        except sqlite3.Error:
            self._storage_error()

    def start(self) -> None:
        """Start or restart observation using the user-selected local port."""
        self._connection_lost()
        try:
            self.store.set_setting("port", str(self.port.value()))
        except sqlite3.Error:
            self._storage_error()
        self.client.start(self.port.value())

    def offer_onboarding(self) -> None:
        """Show optional first-run guidance after the main window is ready."""
        self.onboarding.offer()

    def _receive(self, payload: str) -> None:
        observed_at = datetime.now(UTC)
        try:
            message = self.logs.record_payload(payload, observed_at)
            results = self.tracker.handle(message, observed_at.isoformat())
        except (ValueError, RecursionError) as error:
            LOGGER.warning("Stats API message rejected: %s", error)
            self.notice.setText(T("Message API invalide ignoré ; le suivi continue."))
            self.logs.append_entry(T("Rejet"), str(error), observed_at)
            return
        self.matches.observe(message, self.tracker.status)
        self.evaluations.observe(self.tracker, message)
        self.live.observe(message, observed_at.isoformat(), self.tracker.is_history_replay)
        self._collect_details(message, observed_at.isoformat())
        self._log_observation()
        self._update_players()
        self._save_results(results)

    def _collect_details(self, message: dict[str, object], observed_at: str) -> None:
        """Collect tracked live matches, preserving summaries through disconnections."""
        if self.tracker.is_history_replay or self.tracker.team is None:
            return
        data = message.get("Data")
        if not isinstance(data, dict) or data.get("MatchGuid") != self.tracker.match_id:
            return
        snapshot = self.collector.observe(message, observed_at)
        if snapshot is None or snapshot.replay_active:
            return
        if self.tracker.is_finished or message.get("Event") in (
            "GoalScored",
            "StatfeedEvent",
            "CrossbarHit",
        ):
            try:
                if self._save_detail(snapshot) and self.tracker.is_finished:
                    self._refresh()
            except sqlite3.Error:
                self._storage_error()

    def _save_detail(self, snapshot: MatchSnapshot) -> bool:
        """Write only changed summaries; keep the cache bounded like the collector."""
        signature = snapshot.signature()
        if self._detail_signatures.get(snapshot.guid) == signature:
            return False
        self.store.save_details(snapshot)
        self._detail_signatures = {
            guid: value
            for guid, value in self._detail_signatures.items()
            if guid in self.collector.snapshots
        }
        self._detail_signatures[snapshot.guid] = signature
        return True

    def _log_observation(self) -> None:
        if self.tracker.status != self.observation_status:
            self.observation_status = self.tracker.status
            self.logs.append_entry(T("Suivi"), T(self.observation_status))

    def _update_players(self) -> None:
        options = tuple((player.primary_id, player.name) for player in self.tracker.players)
        if options == self.player_options:
            return
        self.player_options = options
        selector = self.matches.player
        selector.blockSignals(True)
        selector.clear()
        selector.addItem(T("Sélectionne ton joueur dans le match"), "")
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
        self.evaluations.reset_player()
        self.live.set_player(player_id)
        self.selected_name = self.matches.player.currentText()
        self.logs.append_entry(T("Suivi"), T("Sélection du joueur modifiée."))
        try:
            self.store.set_setting("player_id", player_id)
            self.store.set_setting("player_name", self.selected_name)
            self._refresh()
        except sqlite3.Error:
            self._storage_error()

    def _connection_lost(self) -> None:
        self._save_results(self.tracker.interrupt(datetime.now(UTC).isoformat()))
        self.live.clear("Connexion interrompue · valeurs en direct effacées.")
        self.matches.session.setText(T("Partie en cours : en attente de données"))
        self.matches.observation.setText(T(self.tracker.status))
        self.evaluations.show_last()
        self._log_observation()

    def _save_results(self, results: list[MatchResult]) -> None:
        if len(results) == 0:
            return
        try:
            for result in results:
                snapshot = self.collector.snapshots.get(result.match_id)
                if snapshot is not None:
                    self._save_detail(snapshot)
                self.store.save(result)
                self.logs.append_entry(
                    T("Résultat"), f"{result.outcome} • {playlist_label(result.playlist)}"
                )
            self._refresh()
        except sqlite3.Error:
            self._storage_error()

    def _refresh(self) -> None:
        self.matches.refresh(self.store, self.tracker.player_id)

    def _start_session(self) -> None:
        if self.tracker.player_id == "":
            return
        try:
            session_id = self.store.start_session(
                self.tracker.player_id, datetime.now(UTC).isoformat()
            )
            self.matches.period.setCurrentIndex(0)
            self._refresh()
            self.logs.append_entry(
                T("Session"), T("Nouvelle session #{session_id} créée.", session_id=session_id)
            )
        except sqlite3.Error:
            self._storage_error()

    def _storage_error(self) -> None:
        LOGGER.error("Local database operation failed")
        self.notice.setText(
            T("Erreur SQLite : certaines données n’ont pas pu être lues ou enregistrées.")
        )
        self.logs.append_entry("SQLite", self.notice.text())

    def _hotkey_error(self) -> None:
        self.notice.setText(
            T("Raccourcis indisponibles : vérifie leur configuration dans les paramètres.")
        )

    def _save_boost_side(self, side: str) -> None:
        try:
            self.store.set_setting("boost_side", side)
        except sqlite3.Error:
            self._storage_error()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Save an unfinished observation and stop networking before closing."""
        self.onboarding.shutdown()
        self.client.stop()
        self.hotkeys.shutdown()
        self.updates.client.stop()
        self._connection_lost()
        super().closeEvent(event)
