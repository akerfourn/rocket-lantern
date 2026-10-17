"""Documented Win32 window management only: no injection, input hook or game writes."""

import ctypes
import sys
from ctypes import wintypes
from pathlib import PureWindowsPath

type WindowRect = tuple[int, int, int, int]

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
TOPMOST_FLAGS = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GWL_EXSTYLE = -20


def rectangles_overlap(first: WindowRect, second: WindowRect) -> bool:
    return (
        first[0] < second[2]
        and second[0] < first[2]
        and first[1] < second[3]
        and second[1] < first[3]
    )


class WindowsOverlayApi:
    """Keep pointer-sized ctypes signatures explicit, including on Windows x64."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Native overlay management requires Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user32.GetForegroundWindow.argtypes = []
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.EnumWindows.argtypes = [self._enum_callback, wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self.user32.SetWindowPos.restype = wintypes.BOOL
        get_style = self.user32.GetWindowLongW
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            get_style = self.user32.GetWindowLongPtrW
        get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        self._get_style = get_style
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def foreground_window(self) -> int:
        return self.user32.GetForegroundWindow() or 0

    def process_id(self, window: int) -> int:
        process = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(window, ctypes.byref(process))
        return process.value

    def process_name(self, process_id: int) -> str | None:
        """Read only executable identity, never game memory or command-line arguments."""
        process = self.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
        if not process:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if not self.kernel32.QueryFullProcessImageNameW(
                process, 0, buffer, ctypes.byref(length)
            ):
                return None
            return PureWindowsPath(buffer.value).name
        finally:
            self.kernel32.CloseHandle(process)

    def window_rect(self, window: int) -> WindowRect:
        rectangle = wintypes.RECT()
        if not self.user32.GetWindowRect(window, ctypes.byref(rectangle)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (rectangle.left, rectangle.top, rectangle.right, rectangle.bottom)

    def extended_style(self, window: int) -> int:
        return self._get_style(window, GWL_EXSTYLE)

    def is_above(self, overlay: int, game: int) -> bool | None:
        """Take one bounded EnumWindows snapshot instead of traversing changing HWND links."""
        found: list[int] = []

        def collect(window: int, parameter: int) -> bool:
            if window in (overlay, game):
                found.append(window)
            return len(found) < 2

        self.user32.EnumWindows(self._enum_callback(collect), 0)
        if len(found) != 2:
            return None
        return found[0] == overlay

    def promote(self, overlay: int) -> None:
        """Move only our window to the topmost group, without activation or owner changes."""
        if not self.user32.SetWindowPos(overlay, HWND_TOPMOST, 0, 0, 0, 0, TOPMOST_FLAGS):
            raise ctypes.WinError(ctypes.get_last_error())
