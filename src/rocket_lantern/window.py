"""Compact Qt interface for a single player's saved match history."""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from rocket_lantern.boost_overlay_controller import BoostOverlayController
from rocket_lantern.branding import APP_NAME, application_icon
from rocket_lantern.client import StatsClient
from rocket_lantern.evaluation_controller import EvaluationController
from rocket_lantern.game_connection import GameConnectionController
from rocket_lantern.game_presence import GamePresenceMonitor
from rocket_lantern.hotkey_controller import HotkeyController
from rocket_lantern.i18n import language_manager
from rocket_lantern.i18n import text as T
from rocket_lantern.label_catalog import LabelCatalog
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.local_player import LocalPlayer, LocalPlayerLog
from rocket_lantern.local_player_monitor import LocalPlayerMonitor
from rocket_lantern.log_panel import LogPanel
from rocket_lantern.match_data import MatchCollector, MatchSnapshot
from rocket_lantern.match_panel import MatchPanel
from rocket_lantern.onboarding_controller import OnboardingController
from rocket_lantern.overlay_controller import OverlayController
from rocket_lantern.player_encounter_controller import PlayerEncounterController
from rocket_lantern.player_favorites import PlayerFavorites
from rocket_lantern.player_favorites_dialog import PlayerFavoritesDialog
from rocket_lantern.playlists import playlist_label
from rocket_lantern.scoreboard_overlay_controller import ScoreboardOverlayController
from rocket_lantern.settings_panel import SettingsPanel
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult, MatchTracker
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import TranslatedTabWidget as QTabWidget
from rocket_lantern.translated_widgets import tooltip
from rocket_lantern.update_controller import UpdateController

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Coordinate live observations, local persistence and widget updates."""

    def __init__(
        self,
        store: MatchStore,
        presence: GamePresenceMonitor | None = None,
        local_player_log: LocalPlayerLog | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.languages = language_manager()
        saved_language = store.setting("language")
        if saved_language in ("fr", "en"):
            self.languages.set_language(saved_language)
        self.tracker = MatchTracker(store.setting("player_id"))
        self.label_catalog = LabelCatalog(store.labels, self)
        self._local_player: LocalPlayer | None = None
        self._history_player_id = self.tracker.player_id
        self.collector = MatchCollector()
        self._detail_signatures: dict[str, tuple[object, ...]] = {}
        self.selected_name = store.setting("player_name")
        history_player_id = store.setting("history_player_id")
        if history_player_id:
            self._history_player_id = history_player_id
            self.selected_name = store.setting("history_player_name") or history_player_id
        self.player_favorites = PlayerFavorites(store, self)
        if self._history_player_id:
            self.player_favorites.observe(
                (LocalPlayer(self._history_player_id, self.selected_name),)
            )
        self.player_options: tuple[tuple[str, str], ...] = ()
        self.observation_status = ""
        self.client = StatsClient(self)
        self.game_presence = presence
        if self.game_presence is None:
            self.game_presence = GamePresenceMonitor(self)
        else:
            self.game_presence.setParent(self)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(application_icon())
        self.resize(1050, 800)
        self._build_interface()
        self.favorite_players_dialog = PlayerFavoritesDialog(self.player_favorites, self.settings)
        self.favorite_players_dialog.failed.connect(self._storage_error)
        self.settings.manage_players.clicked.connect(self.favorite_players_dialog.open)
        self.player_favorites.changed.connect(self._favorites_changed)
        self.overlay = OverlayController(
            self.settings.overlay, self.matches.counters, self, store, self.game_presence
        )
        self.overlay.failed.connect(self._storage_error)
        self.boost_overlay = BoostOverlayController(
            self.settings.boost_overlay, self.live, self, store, self.game_presence
        )
        self.boost_overlay.failed.connect(self._storage_error)
        self.encounters = PlayerEncounterController(store, self.live, self)
        self.encounters.failed.connect(self._storage_error)
        self.scoreboard_overlay = ScoreboardOverlayController(
            self.settings.scoreboard_overlay, self.live, self, store, self.game_presence
        )
        self.scoreboard_overlay.failed.connect(self._storage_error)
        self.onboarding = OnboardingController(store, self.settings, self)
        self.onboarding.failed.connect(self._storage_error)
        self.onboarding.reconnect_requested.connect(self.start)
        self.evaluations = EvaluationController(store, self.matches, self)
        self.evaluations.failed.connect(self._storage_error)
        self.hotkeys = HotkeyController(self.settings, store)
        self.hotkeys.failed.connect(self._storage_error)
        self.hotkeys.registration_failed.connect(self._hotkey_error)
        self.hotkeys.activated.connect(self.evaluations.vote_current)
        self.label_catalog.changed.connect(self._labels_changed)
        if self.hotkeys.problem is not None:
            self._hotkey_error()
        self.client.message_received.connect(self._receive)
        self.client.status_changed.connect(self._update_status)
        self.languages.changed.connect(self._sync_language)
        self.client.connection_lost.connect(self._connection_lost)
        self.client.diagnostic.connect(self.logs.append_entry)
        self.game_connection = GameConnectionController(self.client, self.game_presence, self)
        self.game_connection.interrupted.connect(self._connection_lost)
        self.local_player_monitor = LocalPlayerMonitor(self, self.game_presence, local_player_log)
        self.local_player_monitor.changed.connect(self._local_player_changed)
        self.logs.append_entry(
            T("Application"), T("Prête ; connexion à la Stats API officielle locale.")
        )
        self._update_players(force=True)
        self._refresh()

        self.game_presence.start()
        self.local_player_monitor.start()
        self.overlay.restore_activation()
        self.boost_overlay.restore_activation()
        self.scoreboard_overlay.restore_activation()

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
        self.matches = MatchPanel(self.tracker.player_id, self.selected_name, self.label_catalog)
        self.matches.player.currentIndexChanged.connect(self._select_player)
        self.matches.favorite_player.clicked.connect(self._toggle_favorite_player)
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
            port,
            self.languages.language,
            self.store.setting("default_tab"),
            self,
            self.label_catalog,
        )
        self.settings.labels.failed.connect(self._storage_error)
        self.matches.counters.overlay_requested.connect(self._show_overlay_settings)
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

    def _labels_changed(self) -> None:
        self.evaluations.refresh()
        self._refresh()
        self.settings.resize_to_contents()

    def _show_settings(self) -> None:
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def _show_overlay_settings(self) -> None:
        self.settings.sections.setCurrentWidget(self.settings.overlay_section)
        self.settings.overlay_tabs.setCurrentWidget(self.settings.overlay)
        self._show_settings()
        self.settings.overlay.enabled.setFocus()

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
        self.game_connection.start(self.port.value())

    def offer_onboarding(self) -> None:
        """Show optional first-run guidance after the main window is ready."""
        self.onboarding.offer()

    def _receive(self, payload: str) -> None:
        observed_at = datetime.now(UTC)
        was_history_replay = self.tracker.is_history_replay
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
        self._collect_details(
            message, observed_at.isoformat(), was_history_replay=was_history_replay
        )
        self._log_observation()
        self._update_players()
        self._save_results(results)

    def _collect_details(
        self, message: dict[str, object], observed_at: str, *, was_history_replay: bool = False
    ) -> None:
        """Record live events independently of the currently selected history player."""
        if self.tracker.is_history_replay or was_history_replay:
            if message.get("Event") == "ReplayCreated":
                self.collector.interrupt(observed_at)
                self._flush_events()
            return
        snapshot = self.collector.observe(message, observed_at)
        if snapshot is None:
            return
        events_saved = self._flush_events()
        if (
            self.tracker.is_finished
            and snapshot.guid == self.tracker.match_id
            and not snapshot.replay_active
        ):
            try:
                if self._save_detail(snapshot) or events_saved:
                    self._refresh()
            except sqlite3.Error:
                self._storage_error()

    def _flush_events(self) -> bool:
        """Commit pending events; a failed transaction leaves them available for retry."""
        saved = False
        try:
            for snapshot in self.collector.snapshots.values():
                if snapshot.events:
                    saved = self._save_detail(snapshot) or saved
        except sqlite3.Error:
            self._storage_error()
        self.collector.prune()
        return saved

    def _save_detail(self, snapshot: MatchSnapshot) -> bool:
        """Write only changed summaries; keep the cache bounded like the collector."""
        signature = snapshot.signature()
        if self._detail_signatures.get(snapshot.guid) == signature:
            return False
        self.store.save_details(snapshot)
        snapshot.events.clear()
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

    def _update_players(self, force: bool = False) -> None:
        options = tuple((player.primary_id, player.name) for player in self.tracker.players)
        if options == self.player_options and not force:
            return
        self.player_options = options
        previous_name = self.selected_name
        selector = self.matches.player
        selector.blockSignals(True)
        selector.clear()
        selector.addItem(T("Sélectionner un joueur…"), "")
        for player in self.tracker.players:
            if (
                self._local_player is not None
                and player.primary_id == self._local_player.primary_id
            ):
                self._local_player = LocalPlayer(player.primary_id, player.name)
            if player.primary_id == self.tracker.player_id:
                self._remember_player(player.primary_id, player.name)
        self.player_favorites.observe(
            tuple(LocalPlayer(player.primary_id, player.name) for player in self.tracker.players)
        )
        if self._local_player is not None:
            self.player_favorites.observe((self._local_player,))
        self._populate_player_choices()
        index = selector.findData(self._history_player_id)
        if index < 0 and self._history_player_id != "":
            name = self.player_favorites.known.get(self._history_player_id, self.selected_name)
            selector.addItem(name, self._history_player_id)
            index = selector.count() - 1
        selector.setCurrentIndex(max(0, index))
        selector.blockSignals(False)
        if self._history_player_id != "":
            self.selected_name = selector.currentText()
        if self.selected_name != previous_name:
            self._refresh()
        self._sync_favorite_player()

    def _populate_player_choices(self) -> None:
        selector = self.matches.player
        favorites = self.player_favorites.players(favorites_only=True)
        seen = {""}
        icon = QIcon(
            self.matches.favorite_player.icon().pixmap(18, 18, QIcon.Mode.Normal, QIcon.State.On)
        )
        for player in favorites:
            selector.addItem(player.name, player.primary_id)
            selector.setItemIcon(selector.count() - 1, icon)
            seen.add(player.primary_id)
        if len(seen) > 1:
            selector.insertSeparator(selector.count())
        players = [LocalPlayer(player.primary_id, player.name) for player in self.tracker.players]
        if self._local_player is not None:
            players.append(self._local_player)
        for player in players:
            if player.primary_id not in seen:
                selector.addItem(player.name, player.primary_id)
                seen.add(player.primary_id)

    def _select_player(self, index: int) -> None:
        player_id = self.matches.player.itemData(index)
        if not isinstance(player_id, str) or player_id == self._history_player_id:
            return
        self._history_player_id = player_id
        self.selected_name = self.matches.player.currentText()
        if self._local_player is None and self.game_presence.state.running is not False:
            self._track_player(player_id)
            self._remember_player(player_id, self.selected_name)
            self.logs.append_entry(T("Suivi"), T("Sélection du joueur modifiée."))
        try:
            self.store.set_settings(
                {"history_player_id": player_id, "history_player_name": self.selected_name}
            )
        except sqlite3.Error:
            self._storage_error()
        self._sync_favorite_player()
        self._refresh()

    def _sync_favorite_player(self) -> None:
        self.matches.favorite_player.set_player(
            self._history_player_id,
            self.selected_name,
            self._history_player_id in self.player_favorites.favorites,
        )

    def _toggle_favorite_player(self, checked: bool) -> None:
        if self._history_player_id == "":
            return
        try:
            self.player_favorites.set_favorite(self._history_player_id, self.selected_name, checked)
        except sqlite3.Error:
            self._sync_favorite_player()
            self._storage_error()

    def _favorites_changed(self) -> None:
        self._update_players(force=True)

    def _track_player(self, player_id: str) -> None:
        if player_id == self.tracker.player_id:
            return
        self._save_results(self.tracker.interrupt(datetime.now(UTC).isoformat()))
        self.tracker.select_player(player_id)
        self.evaluations.reset_player()
        self.live.set_player(player_id)

    def _remember_player(self, player_id: str, name: str) -> None:
        try:
            if (
                self.store.setting("player_id") == player_id
                and self.store.setting("player_name") == name
            ):
                return
            self.store.set_settings({"player_id": player_id, "player_name": name})
        except sqlite3.Error:
            self._storage_error()

    def _local_player_changed(self, player: LocalPlayer | None) -> None:
        self._local_player = player
        if player is None:
            self.live.clear("En attente d’une partie en direct.")
            self._track_player("")
            if self.game_presence.state.running is not False:
                self._history_player_id = ""
                self.selected_name = ""
            self._update_players(force=True)
            self._refresh()
            tooltip(self.matches.player, "")
            self.logs.append_entry(
                T("Suivi"), T("Compte Rocket League non détecté : sélection manuelle disponible.")
            )
            return
        if player.primary_id != self.tracker.player_id:
            self.live.clear("En attente d’une partie en direct.")
        self._track_player(player.primary_id)
        self._history_player_id = player.primary_id
        self.selected_name = player.name
        self._update_players(force=True)
        self._remember_player(player.primary_id, self._local_player.name)
        tooltip(
            self.matches.player,
            T("Filtre l’historique ; la partie en cours suit le compte Rocket League détecté."),
        )
        self._refresh()
        self.logs.append_entry(T("Suivi"), T("Compte Rocket League détecté automatiquement."))

    def _connection_lost(self) -> None:
        observed_at = datetime.now(UTC).isoformat()
        self.collector.interrupt(observed_at)
        self._flush_events()
        self._save_results(self.tracker.interrupt(observed_at))
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
            self.encounters.refresh()
            self._refresh()
        except sqlite3.Error:
            self._storage_error()

    def _refresh(self) -> None:
        self.matches.refresh(self.store, self._history_player_id)

    def _start_session(self) -> None:
        if self._history_player_id == "":
            return
        try:
            session_id = self.store.start_session(
                self._history_player_id, datetime.now(UTC).isoformat()
            )
            self.matches.period.setCurrentIndex(0)
            self._refresh()
            self.encounters.refresh()
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
        self.favorite_players_dialog.close()
        self.onboarding.shutdown()
        self.local_player_monitor.stop()
        self.game_presence.stop()
        self.overlay.shutdown()
        self.boost_overlay.shutdown()
        self.scoreboard_overlay.shutdown()
        self.game_connection.stop()
        self.hotkeys.shutdown()
        self.updates.client.stop()
        self._connection_lost()
        super().closeEvent(event)
