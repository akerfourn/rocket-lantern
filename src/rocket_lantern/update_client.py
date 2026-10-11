"""Nonblocking Qt GitHub checks and streamed, hash-verified installer downloads."""

import hashlib
import json
import logging
from pathlib import Path

from PySide6.QtCore import QIODevice, QObject, QSaveFile, QStandardPaths, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from rocket_lantern.updates import API_URL, UpdateRelease, select_update, version_key

LOGGER = logging.getLogger(__name__)
CHECK_INTERVAL_MS = 10 * 60 * 1000


class UpdateClient(QObject):
    """Keep requests bounded and prevent overlapping checks or downloads."""

    checked = Signal(object)
    failed = Signal()
    busy_changed = Signal(bool)
    downloaded = Signal(str)
    progress = Signal(int)

    def __init__(self, current_version: str, channel: str, parent: QObject) -> None:
        super().__init__(parent)
        self.current_version = current_version
        self.channel = channel
        self.manager = QNetworkAccessManager(self)
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_INTERVAL_MS)
        self.timer.timeout.connect(self.check)
        self.reply: QNetworkReply | None = None
        self._generation = 0
        self._pages: list[object] = []
        self._page = 1
        self._file: QSaveFile | None = None
        self._digest = hashlib.sha256()
        self._size = 0
        self._release: UpdateRelease | None = None
        self._path = ""
        self._download_failed = False

    def start(self) -> None:
        if self.channel != "disabled":
            self.timer.start()
            self.check()

    def set_channel(self, channel: str) -> None:
        self.channel = channel
        self.stop()
        self.start()

    def stop(self) -> None:
        self.timer.stop()
        self._generation += 1
        reply = self.reply
        self.reply = None
        if reply is not None:
            reply.abort()
        if self._file is not None:
            self._file.cancelWriting()
            self._file = None
        self.busy_changed.emit(False)

    def _request(self, url: str, timeout: int = 15000) -> QNetworkReply:
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", b"RocketLantern-update-check")
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setTransferTimeout(timeout)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        reply = self.manager.get(request)
        deadline = QTimer(reply)
        deadline.setSingleShot(True)
        deadline.timeout.connect(reply.abort)
        reply.finished.connect(deadline.stop)
        deadline.start(timeout * 5)
        self.reply = reply
        return reply

    def check(self) -> None:
        if self.channel == "disabled" or self.reply is not None:
            return
        if version_key(self.current_version) is None:
            self.failed.emit()
            return
        self.busy_changed.emit(True)
        self._pages = []
        self._page = 1
        self._fetch_page()

    def _fetch_page(self) -> None:
        generation = self._generation
        reply = self._request(f"{API_URL}?per_page=100&page={self._page}")
        reply.finished.connect(lambda: self._finish_check(reply, generation))
        # Metadata is small; a malformed server response must not fill memory.
        reply.readyRead.connect(lambda: self._limit_metadata(reply))

    @staticmethod
    def _limit_metadata(reply: QNetworkReply) -> None:
        if reply.bytesAvailable() > 8 * 1024 * 1024:
            reply.abort()

    def _finish_check(self, reply: QNetworkReply, generation: int) -> None:
        try:
            if generation != self._generation:
                return
            self.reply = None
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(reply.errorString())
            page = json.loads(bytes(reply.readAll()))
            if not isinstance(page, list):
                raise ValueError("Invalid release metadata")
            self._pages.extend(page)
            if len(page) == 100:
                if self._page >= 10:
                    raise ValueError("Too many release pages")
                self._page += 1
                self._fetch_page()
                return
            self.busy_changed.emit(False)
            self.checked.emit(select_update(self._pages, self.current_version, self.channel))
        except (ValueError, UnicodeError, RecursionError) as error:
            LOGGER.warning("Update check failed: %s", error)
            self.busy_changed.emit(False)
            self.failed.emit()
        finally:
            reply.deleteLater()

    def download(self, release: UpdateRelease) -> None:
        if self.reply is not None or release.download_url == "" or release.digest == "":
            return
        try:
            location = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.CacheLocation
            )
            if location == "":
                raise OSError("No writable update cache")
            directory = Path(location) / "updates"
            directory.mkdir(parents=True, exist_ok=True)
            self._path = str(directory / f"RocketLantern-{release.digest}-setup.exe")
            self._file = QSaveFile(self._path)
            if not self._file.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(self._file.errorString())
        except OSError as error:
            LOGGER.warning("Cannot prepare update download: %s", error)
            self.failed.emit()
            return
        self._release = release
        self._digest = hashlib.sha256()
        self._size = 0
        self._download_failed = False
        self.busy_changed.emit(True)
        generation = self._generation
        reply = self._request(release.download_url, 60000)
        reply.readyRead.connect(lambda: self._read_download(reply, generation))
        reply.finished.connect(lambda: self._finish_download(reply, generation))

    def _read_download(self, reply: QNetworkReply, generation: int) -> None:
        if (
            generation != self._generation
            or self._file is None
            or self._release is None
            or self._download_failed
        ):
            return
        data = bytes(reply.readAll())
        self._size += len(data)
        if self._size > self._release.size or self._file.write(data) != len(data):
            self._download_failed = True
            reply.abort()
            return
        self._digest.update(data)
        self.progress.emit(int(100 * self._size / self._release.size))

    def _finish_download(self, reply: QNetworkReply, generation: int) -> None:
        try:
            if generation != self._generation:
                return
            self._read_download(reply, generation)
            if self.reply is not reply:
                return
            self.reply = None
            valid = (
                not self._download_failed
                and reply.error() == QNetworkReply.NetworkError.NoError
                and self._release is not None
                and self._size == self._release.size
                and self._digest.hexdigest() == self._release.digest
            )
            file = self._file
            self._file = None
            self.busy_changed.emit(False)
            if not valid or file is None:
                if file is not None:
                    file.cancelWriting()
                self.failed.emit()
                return
            if not file.commit():
                self.failed.emit()
                return
            self.downloaded.emit(self._path)
        finally:
            reply.deleteLater()
