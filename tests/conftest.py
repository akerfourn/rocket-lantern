"""Shared offscreen Qt application; no real game or network is used."""

import gc
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QWidget

from rocket_lantern.global_hotkeys import HotkeyBackend
from rocket_lantern.i18n import language_manager
from rocket_lantern.update_client import UpdateClient


@pytest.fixture(autouse=True)
def isolate_windows_hotkeys(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Qt tests must never reserve real shortcuts on the developer's desktop."""
    if "application" not in request.fixturenames:
        return
    backend = Mock(spec=HotkeyBackend)
    backend.register.return_value = True
    monkeypatch.setattr("rocket_lantern.global_hotkeys.WindowsHotkeyBackend", lambda: backend)


@pytest.fixture(scope="session")
def application() -> Iterator[QApplication]:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test", "-platform", "offscreen"])
    language_manager().set_language("fr")
    app.setQuitOnLastWindowClosed(False)
    yield app


@pytest.fixture(autouse=True)
def cleanup_qt_objects(request: pytest.FixtureRequest) -> Iterator[None]:
    """Destroy test-owned Qt objects while QApplication is still alive."""
    if "application" not in request.fixturenames:
        yield
        return
    app = request.getfixturevalue("application")
    initial_windows = set(app.topLevelWidgets())
    initial_clients = set(app.findChildren(UpdateClient))
    yield
    dispose_test_qt_objects(app, initial_windows, initial_clients)


def dispose_test_qt_objects(
    app: QApplication, initial_windows: set[QWidget], initial_clients: set[UpdateClient]
) -> None:
    """Flush deferred deletion before Python tears down the Qt application."""
    # close() hides widgets; deleteLater() alone needs a running event loop.
    for widget in set(app.topLevelWidgets()) - initial_windows:
        widget.deleteLater()
    for client in set(app.findChildren(UpdateClient)) - initial_clients:
        client.stop()
        client.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
