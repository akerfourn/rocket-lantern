"""Read process identities and foreground visibility through documented Win32 APIs."""

import ctypes
from ctypes import wintypes

from rocket_lantern.windows_overlay import WindowsOverlayApi

TH32CS_SNAPPROCESS = 0x00000002
ERROR_NO_MORE_FILES = 18
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
GAME_EXECUTABLE = "rocketleague.exe"


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class WindowsGameApi(WindowsOverlayApi):
    def __init__(self) -> None:
        super().__init__()
        self.kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        for function in (self.kernel32.Process32FirstW, self.kernel32.Process32NextW):
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
            function.restype = wintypes.BOOL
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.IsIconic.argtypes = [wintypes.HWND]
        self.user32.IsIconic.restype = wintypes.BOOL

    def game_process_ids(self) -> frozenset[int]:
        """Keep only Rocket League IDs; never inspect process memory or modules."""
        snapshot = self.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot is None or snapshot == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return self._read_process_ids(snapshot)
        finally:
            self.kernel32.CloseHandle(snapshot)

    def _read_process_ids(self, snapshot: int) -> frozenset[int]:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found: set[int] = set()
        success = self.kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while success:
            if entry.szExeFile.casefold() == GAME_EXECUTABLE:
                found.add(entry.th32ProcessID)
            success = self.kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        error = ctypes.get_last_error()
        if error != ERROR_NO_MORE_FILES:
            raise ctypes.WinError(error)
        return frozenset(found)

    def window_visible(self, window: int) -> bool:
        return bool(self.user32.IsWindowVisible(window)) and not self.user32.IsIconic(window)
