"""Repair overlay Z-order only while Rocket League is foreground, retaining diagnostics."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal

from rocket_lantern.i18n import Text
from rocket_lantern.i18n import text as T
from rocket_lantern.windows_overlay import WindowRect, rectangles_overlap


class OverlayWindowApi(Protocol):
    def foreground_window(self) -> int: ...
    def process_id(self, window: int) -> int: ...
    def process_name(self, process_id: int) -> str | None: ...
    def window_rect(self, window: int) -> WindowRect: ...
    def extended_style(self, window: int) -> int: ...
    def is_above(self, overlay: int, game: int) -> bool | None: ...
    def promote(self, overlay: int) -> None: ...


@dataclass
class OverlayObservation:
    observed_at: str = ""
    game_window: int = 0
    game_rect: WindowRect | None = None
    overlay_rect: WindowRect | None = None
    overlay_extended_style: int | None = None
    overlaps_game: bool | None = None
    above_before: bool | None = None
    above_after: bool | None = None
    placement_requests: int = 0
    error: str = ""

    def diagnostic(self) -> dict[str, object]:
        return asdict(self)


class OverlayMonitor(QObject):
    """A two-Hz check while enabled; never enumerate processes or change another window."""

    status_changed = Signal(object)

    def __init__(
        self,
        api: OverlayWindowApi,
        owner: QObject,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(owner)
        self.api = api
        self._clock = clock
        self.window = 0
        self.observation = OverlayObservation()
        self._foreground = 0
        self._process = 0
        self._is_game = False
        self._status: Text | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.check)

    def start(self, window: int) -> None:
        self.window = window
        self._foreground = 0
        self._process = 0
        self._is_game = False
        self.observation = OverlayObservation()
        self.timer.start()
        self.check()

    def stop(self) -> None:
        self.timer.stop()
        self.window = 0

    def _set_status(self, status: Text) -> None:
        if status != self._status:
            self._status = status
            self.status_changed.emit(status)

    def check(self) -> None:
        if self.window == 0:
            return
        try:
            self._check_foreground()
        except OSError as error:
            self.observation.error = str(error)
            self._set_status(T("Échec du placement Windows. Copiez le diagnostic de l’overlay."))

    def _check_foreground(self) -> None:
        foreground = self.api.foreground_window()
        process = self.api.process_id(foreground)
        changed = (foreground, process) != (self._foreground, self._process)
        if changed:
            name = self.api.process_name(process)
            self._is_game = name is not None and name.casefold() == "rocketleague.exe"
            if name is not None:
                self._foreground = foreground
                self._process = process
        if not self._is_game:
            self._set_status(T("En attente de Rocket League au premier plan."))
            return
        self._observe_game(foreground, changed)

    def _observe_game(self, game: int, entered: bool) -> None:
        state = self.observation
        state.observed_at = self._clock().isoformat(timespec="seconds")
        state.game_window = game
        state.error = ""
        state.game_rect = self.api.window_rect(game)
        state.overlay_rect = self.api.window_rect(self.window)
        state.overlay_extended_style = self.api.extended_style(self.window)
        state.overlaps_game = rectangles_overlap(state.game_rect, state.overlay_rect)
        state.above_before = self.api.is_above(self.window, game)
        state.above_after = state.above_before
        if entered or state.above_before is not True:
            self.api.promote(self.window)
            state.placement_requests += 1
            state.above_after = self.api.is_above(self.window, game)
        if not state.overlaps_game:
            self._set_status(
                T("Overlay hors de la fenêtre du jeu : vérifiez l’écran et la position.")
            )
        elif state.above_after is True:
            self._set_status(T("Rocket League détecté · placement Windows au-dessus confirmé."))
        else:
            self._set_status(
                T("Ordre des fenêtres non confirmé. Copiez le diagnostic de l’overlay.")
            )
