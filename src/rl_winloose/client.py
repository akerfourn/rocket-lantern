"""Qt-native, local-only WebSocket connection with bounded reconnect delay."""

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket, QNetworkProxy
from PySide6.QtWebSockets import QWebSocket


class StatsClient(QObject):
    """Receive game events on the Qt event loop without worker threads."""

    message_received = Signal(str)
    status_changed = Signal(str)
    connection_lost = Signal()
    diagnostic = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.socket = QWebSocket(parent=self)
        self.socket.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.socket.setMaxAllowedIncomingMessageSize(1_048_576)
        self.socket.textMessageReceived.connect(self._receive_text)
        self.socket.binaryMessageReceived.connect(self._receive_binary)
        self.socket.connected.connect(self._connected)
        self.socket.disconnected.connect(self._disconnected)
        self.socket.errorOccurred.connect(self._error)
        self.retry = QTimer(self)
        self.retry.setSingleShot(True)
        self.retry.timeout.connect(self._connect)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timed_out)
        self.silence = QTimer(self)
        self.silence.setSingleShot(True)
        self.silence.timeout.connect(self._silent)
        self.has_received_message = False
        self.is_silent = False
        self.is_running = False
        self.port = 49124

    def start(self, port: int) -> None:
        """Connect to the game's loopback WebSocket at the configured port."""
        if not 1 <= port <= 65535:
            raise ValueError("Le port doit être compris entre 1 et 65535.")
        self.stop()
        self.port = port
        self.is_running = True
        self._connect()

    def stop(self) -> None:
        """Cancel retries and release the socket immediately."""
        self.is_running = False
        self.retry.stop()
        self.timeout.stop()
        self.silence.stop()
        self.socket.abort()

    def _connect(self) -> None:
        if not self.is_running:
            return
        if self.socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            return
        self._status(f"Connexion à ws://127.0.0.1:{self.port}…")
        self.timeout.start(5000)
        self.socket.open(QUrl(f"ws://127.0.0.1:{self.port}"))

    def _connected(self) -> None:
        self.timeout.stop()
        self.retry.stop()
        self.has_received_message = False
        self.is_silent = False
        self.silence.start(10000)
        self._status("WebSocket connecté • en attente des événements du match")

    def _disconnected(self) -> None:
        self.timeout.stop()
        self.silence.stop()
        self.diagnostic.emit("Déconnexion", f"Code WebSocket : {self.socket.closeCode().name}")
        self.connection_lost.emit()
        if self.is_running:
            self._status("Jeu déconnecté • nouvelle tentative dans 3 s")
            self.retry.start(3000)

    def _error(self, error: QAbstractSocket.SocketError) -> None:
        self.timeout.stop()
        self.silence.stop()
        if self.is_running:
            self.diagnostic.emit("Erreur WebSocket", f"{error.name} : {self.socket.errorString()}")
            self._status("API indisponible • vérifie le jeu et sa configuration")
            self.retry.start(3000)

    def _timed_out(self) -> None:
        self.socket.abort()
        if self.is_running:
            self._status("Connexion expirée • nouvelle tentative dans 3 s")
            self.retry.start(3000)

    def _status(self, message: str) -> None:
        self.status_changed.emit(message)
        self.diagnostic.emit("Connexion", message)

    def _silent(self) -> None:
        if not self.is_running:
            return
        self.is_silent = True
        self._status(
            "WebSocket connecté, mais aucun événement depuis 10 s : "
            "menu du jeu ou configuration Stats API à vérifier."
        )

    def _receive_text(self, payload: str) -> None:
        self.silence.start(10000)
        if not self.has_received_message or self.is_silent:
            self._status("Connecté • événements reçus")
        self.has_received_message = True
        self.is_silent = False
        self.message_received.emit(payload)

    def _receive_binary(self, payload: QByteArray) -> None:
        try:
            text = bytes(payload).decode("utf-8")
        except UnicodeDecodeError:
            self.diagnostic.emit("Trame ignorée", f"Binaire non UTF-8 : {len(payload)} octets")
            return
        self.diagnostic.emit("Transport", "Trame binaire décodée en UTF-8")
        self._receive_text(text)
