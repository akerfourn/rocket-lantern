"""Native process enumeration contract: exact names, explicit errors, closed handles."""

import ctypes
import sys
from unittest.mock import Mock

import pytest

from rocket_lantern.windows_game import (
    ERROR_NO_MORE_FILES,
    INVALID_HANDLE_VALUE,
    TH32CS_SNAPPROCESS,
    ProcessEntry,
    WindowsGameApi,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Win32 ABI and last-error semantics"
)


def api_with_entries(entries: list[tuple[int, str]]) -> WindowsGameApi:
    api = object.__new__(WindowsGameApi)
    api.kernel32 = Mock()
    api.user32 = Mock()
    api.kernel32.CreateToolhelp32Snapshot.return_value = 123
    pending = iter(entries)

    def advance(snapshot: int, pointer: object) -> bool:
        assert snapshot == 123
        record = ctypes.cast(pointer, ctypes.POINTER(ProcessEntry)).contents
        assert record.dwSize == ctypes.sizeof(ProcessEntry)
        item = next(pending, None)
        if item is None:
            ctypes.set_last_error(ERROR_NO_MORE_FILES)
            return False
        record.th32ProcessID, record.szExeFile = item
        return True

    api.kernel32.Process32FirstW.side_effect = advance
    api.kernel32.Process32NextW.side_effect = advance
    return api


def test_game_processes_should_match_exact_executable_names_case_insensitively() -> None:
    api = api_with_entries(
        [
            (10, "RocketLeague.exe"),
            (11, "ROCKETLEAGUE.EXE"),
            (12, "RocketLeagueLauncher.exe"),
            (13, "Other.exe"),
        ]
    )

    assert api.game_process_ids() == frozenset({10, 11})
    api.kernel32.CreateToolhelp32Snapshot.assert_called_once_with(TH32CS_SNAPPROCESS, 0)
    api.kernel32.CloseHandle.assert_called_once_with(123)


def test_game_processes_should_return_empty_when_snapshot_has_no_entries() -> None:
    api = api_with_entries([])

    assert api.game_process_ids() == frozenset()
    api.kernel32.CloseHandle.assert_called_once_with(123)


def test_game_processes_should_raise_without_closing_an_invalid_snapshot_handle() -> None:
    api = api_with_entries([])
    api.kernel32.CreateToolhelp32Snapshot.return_value = INVALID_HANDLE_VALUE
    ctypes.set_last_error(5)

    with pytest.raises(OSError, match=".+"):
        api.game_process_ids()

    api.kernel32.CloseHandle.assert_not_called()


def test_game_processes_should_close_snapshot_and_raise_instead_of_reporting_absence_on_error() -> (
    None
):
    api = api_with_entries([])
    api.kernel32.Process32FirstW.side_effect = None
    api.kernel32.Process32FirstW.return_value = False
    ctypes.set_last_error(5)

    with pytest.raises(OSError, match=".+"):
        api.game_process_ids()

    api.kernel32.CloseHandle.assert_called_once_with(123)


@pytest.mark.parametrize(
    ("visible", "minimized", "expected"),
    [
        (True, False, True),
        (True, True, False),
        (False, False, False),
    ],
)
def test_window_visibility_should_exclude_minimized_windows(
    visible: bool, minimized: bool, expected: bool
) -> None:
    api = api_with_entries([])
    api.user32.IsWindowVisible.return_value = visible
    api.user32.IsIconic.return_value = minimized

    assert api.window_visible(10) == expected
