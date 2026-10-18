"""Gate API attempts on game lifetime, never on focus or minimization."""

from PySide6.QtCore import QObject, Signal

from rocket_lantern.client import StatsClient
from rocket_lantern.game_presence import GamePresence, GamePresenceMonitor


class GameConnectionController(QObject):
    interrupted = Signal()

    def __init__(self, client: StatsClient, presence: GamePresenceMonitor, owner: QObject) -> None:
        super().__init__(owner)
        self.client = client
        self.presence = presence
        self._requested = False
        self._port = 49124
        presence.changed.connect(self._presence_changed)

    def start(self, port: int) -> None:
        self._requested = True
        self._port = port
        self._reconcile(restart=True)

    def stop(self) -> None:
        self._requested = False
        self.client.stop()

    def _presence_changed(self, state: GamePresence) -> None:
        if self._requested:
            self._reconcile()

    def _reconcile(self, restart: bool = False) -> None:
        running = self.presence.state.running
        if running is False:
            was_running = self.client.is_running
            self.client.wait_for_game()
            if was_running:
                self.interrupted.emit()
            return
        # Unknown detection must not terminate an existing recording. Explicit reconnect
        # remains available if detection is unsupported or temporarily unavailable.
        if running is None and self.presence.supported and not restart:
            return
        if restart or not self.client.is_running:
            self.client.start(self._port)
