"""Native hotkey contracts with mocked Windows calls, never real keyboard capture."""

import ctypes
from collections.abc import Iterator
from ctypes import wintypes
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QWidget

from rocket_lantern.global_hotkeys import (
    DEFAULT_HOTKEYS,
    MOD_NOREPEAT,
    WM_HOTKEY,
    GlobalHotkeys,
    Hotkey,
    HotkeyBackend,
    HotkeyError,
    HotkeyProblem,
    WindowsHotkeyBackend,
    parse_hotkey,
    validate_hotkeys,
)


@pytest.fixture
def manager(application: QApplication) -> Iterator[GlobalHotkeys]:
    parent = QWidget()
    backend = Mock(spec=HotkeyBackend)
    backend.register.return_value = True
    widget = GlobalHotkeys(parent, backend)
    yield widget
    widget.stop()
    parent.deleteLater()


def test_defaults_should_register_the_requested_ctrl_shift_f1_to_f4() -> None:
    assert validate_hotkeys(DEFAULT_HOTKEYS) == tuple(Hotkey(6, key) for key in range(0x70, 0x74))


@pytest.mark.parametrize(
    "value",
    ["", "F1", "Ctrl+F12", "Ctrl+F35", "Meta+F1", "Ctrl+F1, Ctrl+F2", "Ctrl+Space", "nonsense"],
)
def test_parser_should_reject_unsupported_or_reserved_shortcuts(value: str) -> None:
    with pytest.raises(HotkeyError, match="invalid"):
        parse_hotkey(value)


def test_parser_should_accept_supported_custom_chords_and_reject_duplicates() -> None:
    assert parse_hotkey("Alt+Shift+A") == Hotkey(5, ord("A"))
    assert parse_hotkey("Ctrl+9") == Hotkey(2, ord("9"))
    assert parse_hotkey("Shift+F24") == Hotkey(4, 0x87)
    with pytest.raises(HotkeyError, match="duplicate"):
        validate_hotkeys(("Ctrl+F1", "Ctrl+F1", "Ctrl+F3", "Ctrl+F4"))
    with pytest.raises(HotkeyError, match="invalid"):
        validate_hotkeys(("Ctrl+F1",))


def test_manager_should_register_and_dispatch_only_known_ids_then_release_them(
    manager: GlobalHotkeys,
) -> None:
    received: list[str] = []
    manager.activated.connect(received.append)
    manager.start(DEFAULT_HOTKEYS)
    identifiers = [call.args[0] for call in manager.backend.register.call_args_list]
    assert manager.dispatch(123) is False
    for identifier in identifiers:
        assert manager.dispatch(identifier)
    assert received == ["not_evaluated", "no_suspicion", "possible", "strong"]
    manager.stop()
    assert [call.args[0] for call in manager.backend.unregister.call_args_list] == identifiers
    assert manager.dispatch(identifiers[0]) is False


def test_manager_should_roll_back_partial_registration_on_a_conflict(
    manager: GlobalHotkeys,
) -> None:
    manager.backend.register.side_effect = [True, True, False]
    with pytest.raises(HotkeyError, match="conflict"):
        manager.start(DEFAULT_HOTKEYS)
    registered = [call.args[0] for call in manager.backend.register.call_args_list[:2]]
    assert [call.args[0] for call in manager.backend.unregister.call_args_list] == registered
    assert not manager._active
    assert not manager._installed


def test_manager_should_release_partial_registration_when_windows_raises(
    manager: GlobalHotkeys,
) -> None:
    manager.backend.register.side_effect = [True, OSError("Windows call failed")]
    with pytest.raises(OSError, match="Windows call failed"):
        manager.start(DEFAULT_HOTKEYS)
    manager.backend.unregister.assert_called_once_with(
        manager.backend.register.call_args_list[0].args[0]
    )
    assert not manager._active


def test_native_filter_should_handle_hotkey_messages_but_not_other_events(
    manager: GlobalHotkeys,
) -> None:
    received: list[str] = []
    manager.activated.connect(received.append)
    manager.start(DEFAULT_HOTKEYS)
    identifier = manager.backend.register.call_args_list[2].args[0]
    message = wintypes.MSG()
    message.message = WM_HOTKEY
    message.wParam = identifier
    pointer = ctypes.addressof(message)
    assert manager._filter.nativeEventFilter(b"windows_dispatcher_MSG", pointer) == (True, 0)
    assert received == ["possible"]
    message.message = 0x0100
    assert manager._filter.nativeEventFilter(b"windows_generic_MSG", pointer) == (False, 0)
    assert manager._filter.nativeEventFilter(b"xcb_generic_event_t", 0) == (False, 0)
    assert received == ["possible"]


def test_manager_should_stop_when_its_parent_is_destroyed(application: QApplication) -> None:
    parent = QWidget()
    backend = Mock(spec=HotkeyBackend)
    backend.register.return_value = True
    manager = GlobalHotkeys(parent, backend)
    manager.start(DEFAULT_HOTKEYS)
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert backend.unregister.call_count == 4


def test_backend_should_use_typed_windows_calls_and_disable_auto_repeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = Mock()
    library.RegisterHotKey.return_value = 1
    library.UnregisterHotKey.return_value = 1
    loader = Mock(return_value=library)
    monkeypatch.setattr(ctypes, "WinDLL", loader, raising=False)
    backend = WindowsHotkeyBackend()
    assert backend.register(42, Hotkey(6, 0x70))
    library.RegisterHotKey.assert_called_once_with(None, 42, 6 | MOD_NOREPEAT, 0x70)
    backend.unregister(42)
    library.UnregisterHotKey.assert_called_once_with(None, 42)
    loader.assert_called_once_with("user32", use_last_error=True)
    assert library.RegisterHotKey.restype == wintypes.BOOL


def test_manager_should_not_load_windows_library_until_enabled(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = Mock()
    monkeypatch.setattr("rocket_lantern.global_hotkeys.WindowsHotkeyBackend", loader)
    parent = QWidget()
    manager = GlobalHotkeys(parent)
    manager.stop()
    loader.assert_not_called()


def test_manager_should_report_unsupported_platform_without_loading_windows(
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("rocket_lantern.global_hotkeys.sys.platform", "linux")
    parent = QWidget()
    manager = GlobalHotkeys(parent)
    with pytest.raises(HotkeyError) as error:
        manager.start(DEFAULT_HOTKEYS)
    assert error.value.problem == HotkeyProblem.UNSUPPORTED
