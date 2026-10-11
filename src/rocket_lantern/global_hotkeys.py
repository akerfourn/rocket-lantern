"""Opt-in Windows hotkeys; no keyboard hook, polling or game interaction."""

import ctypes
import logging
import sys
from ctypes import wintypes
from dataclasses import dataclass
from enum import StrEnum
from itertools import count
from typing import Protocol

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Qt, Signal
from PySide6.QtGui import QKeySequence

from rocket_lantern.evaluations import Evaluation

LOGGER = logging.getLogger(__name__)
DEFAULT_HOTKEYS = tuple(f"Ctrl+Shift+F{index}" for index in range(1, 5))
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


class HotkeyProblem(StrEnum):
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


class HotkeyError(ValueError):
    def __init__(self, problem: HotkeyProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


@dataclass(frozen=True)
class Hotkey:
    modifiers: int
    key: int


def parse_hotkey(value: str) -> Hotkey:
    """Allow one Ctrl/Alt/Shift chord with a letter, digit or supported function key."""
    sequence = QKeySequence.fromString(value, QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1:
        raise HotkeyError(HotkeyProblem.INVALID)
    combination = sequence[0]
    modifiers = combination.keyboardModifiers()
    allowed = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    allowed |= Qt.KeyboardModifier.ShiftModifier
    if modifiers.value == 0 or modifiers.value & ~allowed.value:
        raise HotkeyError(HotkeyProblem.INVALID)
    key = combination.key().value
    if Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F24.value:
        if key == Qt.Key.Key_F12.value:
            raise HotkeyError(HotkeyProblem.INVALID)
        virtual_key = 0x70 + key - Qt.Key.Key_F1.value
    elif ord("A") <= key <= ord("Z") or ord("0") <= key <= ord("9"):
        virtual_key = key
    else:
        raise HotkeyError(HotkeyProblem.INVALID)
    native_modifiers = 0
    for modifier, native in (
        (Qt.KeyboardModifier.AltModifier, 1),
        (Qt.KeyboardModifier.ControlModifier, 2),
        (Qt.KeyboardModifier.ShiftModifier, 4),
    ):
        if modifiers & modifier:
            native_modifiers |= native
    return Hotkey(native_modifiers, virtual_key)


def validate_hotkeys(values: tuple[str, ...]) -> tuple[Hotkey, ...]:
    if len(values) != len(Evaluation):
        raise HotkeyError(HotkeyProblem.INVALID)
    hotkeys = tuple(parse_hotkey(value) for value in values)
    if len(set(hotkeys)) != len(hotkeys):
        raise HotkeyError(HotkeyProblem.DUPLICATE)
    return hotkeys


class HotkeyBackend(Protocol):
    def register(self, identifier: int, hotkey: Hotkey) -> bool: ...
    def unregister(self, identifier: int) -> None: ...


class WindowsHotkeyBackend:
    def __init__(self) -> None:
        self._library = ctypes.WinDLL("user32", use_last_error=True)
        self._register = self._library.RegisterHotKey
        self._register.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._register.restype = wintypes.BOOL
        self._unregister = self._library.UnregisterHotKey
        self._unregister.argtypes = [wintypes.HWND, ctypes.c_int]
        self._unregister.restype = wintypes.BOOL

    def register(self, identifier: int, hotkey: Hotkey) -> bool:
        return bool(self._register(None, identifier, hotkey.modifiers | MOD_NOREPEAT, hotkey.key))

    def unregister(self, identifier: int) -> None:
        if not self._unregister(None, identifier):
            LOGGER.warning("Cannot unregister global hotkey %s", identifier)


class HotkeyEventFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "GlobalHotkeys") -> None:
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type: bytes, message: int) -> tuple[bool, int]:
        if event_type not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0
        native = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
        if native.message != WM_HOTKEY:
            return False, 0
        return self.owner.dispatch(int(native.wParam)), 0


class GlobalHotkeys(QObject):
    activated = Signal(str)
    _groups = count()

    def __init__(self, parent: QObject, backend: HotkeyBackend | None = None) -> None:
        super().__init__(parent)
        self.backend = backend
        base_identifier = 0x5200 + next(self._groups) * 4
        self._identifiers = tuple(base_identifier + index for index in range(4))
        self._active: dict[int, Evaluation] = {}
        self._filter = HotkeyEventFilter(self)
        self._installed = False
        parent.destroyed.connect(self.stop)

    def start(self, values: tuple[str, ...]) -> None:
        """Register all four or none; disabled operation never loads user32."""
        hotkeys = validate_hotkeys(values)
        self.stop()
        if self.backend is None:
            if sys.platform != "win32":
                raise HotkeyError(HotkeyProblem.UNSUPPORTED)
            self.backend = WindowsHotkeyBackend()
        try:
            for identifier, value, hotkey in zip(
                self._identifiers, Evaluation, hotkeys, strict=True
            ):
                if not self.backend.register(identifier, hotkey):
                    raise HotkeyError(HotkeyProblem.CONFLICT)
                self._active[identifier] = value
        except (OSError, HotkeyError):
            self.stop()
            raise
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        self._installed = True

    def stop(self) -> None:
        """Release registered combinations and remove the native event filter."""
        if self.backend is not None:
            for identifier in self._active:
                self.backend.unregister(identifier)
        self._active.clear()
        if self._installed:
            QCoreApplication.instance().removeNativeEventFilter(self._filter)
            self._installed = False

    def dispatch(self, identifier: int) -> bool:
        """Only registered IDs emit votes; unrelated native messages are untouched."""
        value = self._active.get(identifier)
        if value is None:
            return False
        self.activated.emit(value.value)
        return True
