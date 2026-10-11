"""Qt objects must be destroyed before the shared application shuts down."""

from unittest.mock import Mock

from conftest import dispose_test_qt_objects
from PySide6.QtWidgets import QApplication, QWidget

from rocket_lantern.update_client import UpdateClient


def test_cleanup_should_destroy_closed_windows_and_clients_while_application_is_alive(
    application: QApplication,
) -> None:
    initial_windows = set(application.topLevelWidgets())
    initial_clients = set(application.findChildren(UpdateClient))
    window = QWidget()
    client = UpdateClient("1.0.0", "disabled", application)
    window_destroyed = Mock()
    client_destroyed = Mock()
    window.destroyed.connect(window_destroyed)
    client.destroyed.connect(client_destroyed)
    window.close()

    dispose_test_qt_objects(application, initial_windows, initial_clients)

    window_destroyed.assert_called_once()
    client_destroyed.assert_called_once()
    assert set(application.findChildren(UpdateClient)) == initial_clients
    assert set(application.topLevelWidgets()) == initial_windows
