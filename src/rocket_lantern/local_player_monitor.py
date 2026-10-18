"""Follow account changes only while Rocket League is running."""

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from time import time

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from rocket_lantern.game_presence import GamePresenceMonitor
from rocket_lantern.local_player import LocalPlayer, LocalPlayerLog

LOGGER = logging.getLogger(__name__)


def default_log_path() -> Path | None:
    """Honor Windows' redirected Documents folder, including OneDrive."""
    if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
        return None
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    if documents == "":
        return None
    return Path(documents) / "My Games/Rocket League/TAGame/Logs/Launch.log"


class LocalPlayerMonitor(QObject):
    changed = Signal(object)

    def __init__(
        self,
        owner: QObject,
        presence: GamePresenceMonitor,
        source: LocalPlayerLog | None = None,
        clock: Callable[[], float] = time,
    ) -> None:
        super().__init__(owner)
        self.presence = presence
        self.source = source
        if source is None:
            path = default_log_path()
            if path is not None:
                self.source = LocalPlayerLog(path)
        self.player: LocalPlayer | None = None
        self._clock = clock
        self._not_before = 0.0
        self._running = False
        self._process_ids: frozenset[int] | None = None
        self._last_check = 0.0
        self._active = False
        self._error: tuple[type[OSError], int | None] | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.check)
        presence.changed.connect(self.check)

    def start(self) -> None:
        if self._active or self.source is None:
            return
        self._active = True
        self.check()
        self.timer.start()

    def stop(self) -> None:
        self._active = False
        self.timer.stop()

    def check(self) -> None:
        if not self._active or self.source is None:
            return
        self.timer.setInterval(2000)
        running = self.presence.state.running
        if running is None:
            return
        checked_at = self._clock()
        if running is False:
            self._not_before = checked_at
            self._last_check = checked_at
            self._process_ids = None
            self._running = False
            self.source.reset()
            self._publish(None)
            return
        process_ids = self.presence.process_ids
        if self._process_ids is not None and process_ids != self._process_ids:
            self._not_before = self._last_check
            self._running = False
            self._publish(None)
        self._process_ids = process_ids
        self._last_check = checked_at
        if not self._running:
            self.source.reset()
            self._running = True
        try:
            player = self.source.read(self._not_before)
        except OSError as error:
            signature = (type(error), error.errno)
            if signature != self._error:
                LOGGER.warning("Local player log unavailable (errno=%s)", error.errno)
            self._error = signature
            self._publish(None)
            return
        self._error = None
        if self.source.ready:
            self._publish(player)
        else:
            if self.source.player is None:
                self._publish(None)
            # Catch up large startup logs over event-loop turns, not two-second waits.
            self.timer.setInterval(0)

    def _publish(self, player: LocalPlayer | None) -> None:
        if player != self.player:
            self.player = player
            self.changed.emit(player)
