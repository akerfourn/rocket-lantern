"""Transport signals with network opening replaced at the socket boundary."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QByteArray, QUrl
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWidgets import QApplication

from rocket_lantern.client import StatsClient


@pytest.fixture
def client(application: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[StatsClient]:
    connection = StatsClient()

    def open_without_network(url: QUrl) -> None:
        connection.socket.connected.emit()

    monkeypatch.setattr(connection.socket, "open", open_without_network)
    yield connection
    connection.stop()


def test_client_should_report_silent_connection_when_no_events_arrive(client: StatsClient) -> None:
    messages = []
    client.status_changed.connect(messages.append)
    client.start(49124)

    client.silence.timeout.emit()

    assert "aucun événement depuis 10 s" in messages[-1]
    client.socket.textMessageReceived.emit('{"Event":"GoalScored","Data":{}}')
    assert messages[-1] == "Connecté • événements reçus"


def test_client_should_forward_binary_json_when_server_uses_binary_frames(
    client: StatsClient,
) -> None:
    messages = []
    client.message_received.connect(messages.append)
    client.start(49124)

    client.socket.binaryMessageReceived.emit(QByteArray(b'{"Event":"MatchCreated","Data":{}}'))

    assert messages == ['{"Event":"MatchCreated","Data":{}}']


def test_client_should_show_socket_error_when_connection_is_refused(client: StatsClient) -> None:
    diagnostics = []

    def record(category: str, details: str) -> None:
        diagnostics.append((category, details))

    client.diagnostic.connect(record)
    client.start(49124)

    client.socket.errorOccurred.emit(QAbstractSocket.SocketError.ConnectionRefusedError)

    assert any("ConnectionRefusedError" in details for _, details in diagnostics)
    assert client.retry.isActive()
    client.stop()
    assert not client.retry.isActive()
    assert not client.silence.isActive()
