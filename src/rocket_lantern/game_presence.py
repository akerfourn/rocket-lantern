"""One shared detector for game lifetime and foreground-only overlay visibility."""

import logging
import sys
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from rocket_lantern.windows_game import WindowsGameApi

LOGGER = logging.getLogger(__name__)


class GamePresenceApi(Protocol):
    def game_process_ids(self) -> frozenset[int]: ...
    def foreground_window(self) -> int: ...
    def process_id(self, window: int) -> int: ...
    def window_visible(self, window: int) -> bool: ...


@dataclass(frozen=True)
class GamePresence:
    running: bool | None = None
    foreground: bool = False
    window: int = 0


class GamePresenceMonitor(QObject):
    """Check foreground every 500 ms and process presence every two seconds."""

    changed = Signal(object)
    polled = Signal()

    def __init__(self, owner: QObject, api: GamePresenceApi | None = None) -> None:
        super().__init__(owner)
        self.supported = api is not None or (
            sys.platform == "win32" and QGuiApplication.platformName() == "windows"
        )
        self.api = api
        self.state = GamePresence()
        self._process_ids: frozenset[int] = frozenset()
        self._scan_ticks = 0
        self._active = False
        self._error = ""
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.check)

    def start(self) -> None:
        if not self.supported or self._active:
            return
        self._active = True
        self._scan_ticks = 0
        self.check()
        self.timer.start()

    def stop(self) -> None:
        self._active = False
        self.timer.stop()

    def check(self) -> None:
        if not self._active:
            return
        try:
            if self.api is None:
                self.api = WindowsGameApi()
            if self._scan_ticks == 0:
                self._process_ids = self.api.game_process_ids()
                self._scan_ticks = 4
            self._scan_ticks -= 1
        except OSError as error:
            self._report_error(error)
            self._publish(GamePresence())
            return
        try:
            state = self._foreground_state()
        except OSError as error:
            self._report_error(error)
            self._publish(GamePresence(running=bool(self._process_ids)))
            return
        self._error = ""
        self._publish(state)

    def _foreground_state(self) -> GamePresence:
        running = bool(self._process_ids)
        if not running:
            return GamePresence(running=False)
        window = self.api.foreground_window()
        if window == 0 or self.api.process_id(window) not in self._process_ids:
            return GamePresence(running=True)
        if not self.api.window_visible(window):
            return GamePresence(running=True)
        return GamePresence(running=True, foreground=True, window=window)

    def _publish(self, state: GamePresence) -> None:
        if state != self.state:
            self.state = state
            self.changed.emit(state)
        self.polled.emit()

    def _report_error(self, error: OSError) -> None:
        message = str(error)
        if message != self._error:
            LOGGER.warning("Rocket League detection unavailable: %s", error)
            self._error = message

    @property
    def allows_overlay(self) -> bool:
        return not self.supported or self.state.foreground
