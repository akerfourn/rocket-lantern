"""Connect persistent rules, live account context, previews and asynchronous audio."""

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QObject, QTimer, Signal

from rocket_lantern.i18n import text as T
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.sound_alert_engine import AlertContext, SoundAlertEngine
from rocket_lantern.sound_alert_settings import SoundAlertSettings
from rocket_lantern.sound_alerts import SoundAlertConfig, SoundRef, parse_sound_config
from rocket_lantern.sound_library import SoundLibrary
from rocket_lantern.sound_player import SoundPlayer
from rocket_lantern.storage import MatchStore

LOGGER = logging.getLogger(__name__)


class SoundAlertController(QObject):
    failed = Signal()

    def __init__(
        self,
        controls: SoundAlertSettings,
        live: LiveMatchPanel,
        store: MatchStore,
        parent: QObject,
        *,
        player: SoundPlayer | None = None,
        library: SoundLibrary | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        super().__init__(parent)
        self.controls = controls
        self.live = live
        self.store = store
        self.clock = clock
        self._closing = False
        self._history_replay = False
        self.config = SoundAlertConfig()
        saved = store.setting("sound_alerts")
        if saved:
            try:
                self.config = parse_sound_config(saved)
            except (ValueError, TypeError, RecursionError) as error:
                LOGGER.warning("Ignoring invalid sound alert settings: %s", error)
                controls.status.setText(
                    T("Impossible de charger les réglages des alertes sonores.")
                )
        self.engine = SoundAlertEngine(self.config)
        self.player = player
        if self.player is None:
            self.player = SoundPlayer(self)
        self.library = library
        if self.library is None:
            filename = store.connection.execute("PRAGMA database_list").fetchone()["file"]
            directory = None
            if filename:
                directory = Path(filename).parent
            self.library = SoundLibrary(directory)
        controls.library = self.library
        controls.set_config(self.config)
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._flush)
        self.player.failed.connect(self._audio_error)
        controls.config_changed.connect(self._save)
        controls.preview_requested.connect(self._preview)
        live.state_changed.connect(self._context_changed)

    def _context(self) -> AlertContext:
        return AlertContext(
            self.live.state.snapshot,
            self.live.player_id,
            self._history_replay or self.live.state.goal_replay,
        )

    def _context_changed(self) -> None:
        if self._closing:
            return
        context = self._context()
        self.engine.sync_context(context)
        if context.snapshot is None:
            self.timer.stop()
            self.player.stop()

    def observe(self, message: dict[str, object], history_replay: bool) -> None:
        if self._closing:
            return
        self._history_replay = history_replay
        for rule in self.engine.observe(message, self._context(), self.clock()):
            self._play(rule.sound)
        if self.engine.pending:
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()

    def _flush(self) -> None:
        if self._closing:
            return
        for rule in self.engine.flush(self._context(), self.clock()):
            self._play(rule.sound)
        if not self.engine.pending:
            self.timer.stop()

    def _save(self, config: SoundAlertConfig) -> None:
        if self._closing or config == self.config:
            return
        try:
            self.store.set_setting("sound_alerts", config.serialize())
        except sqlite3.Error:
            self.controls.set_config(self.config)
            self.controls.status.setText(T("Impossible d’enregistrer les paramètres."))
            self.failed.emit()
            return
        mode_changed = config.mode != self.config.mode
        self.config = config
        self.engine.configure(config)
        self.timer.stop()
        if mode_changed:
            self.player.stop()
        self.player.set_volume(config.volume)
        self.controls.set_config(config)
        self.controls.status.clear()

    def _play(self, sound: SoundRef) -> None:
        try:
            path = self.library.resolve(sound)
        except OSError as error:
            self._audio_error(str(error))
            return
        self.player.play(path, self.config.volume)

    def _preview(self, sound: SoundRef) -> None:
        if not self._closing:
            self.controls.status.clear()
            self._play(sound)

    def _audio_error(self, message: str) -> None:
        if self._closing:
            return
        notice = T("Impossible de lire le son : {error}", error=message)
        self.controls.status.setText(notice)
        if self.controls.editor is not None:
            self.controls.editor.status.setText(notice)

    def shutdown(self) -> None:
        self._closing = True
        self.timer.stop()
        self.engine.clear()
        self.player.stop()
        if self.controls.editor is not None:
            self.controls.editor.reject()
