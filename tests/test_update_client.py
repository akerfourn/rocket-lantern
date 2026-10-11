"""Exercise Qt update requests using fake replies, never a real network."""

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QByteArray, QObject, QStandardPaths, Signal
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication

from rocket_lantern.update_client import CHECK_INTERVAL_MS, UpdateClient
from rocket_lantern.updates import RELEASE_URL, UpdateRelease


class FakeReply(QObject):
    readyRead = Signal()
    finished = Signal()

    def __init__(self, body: bytes = b"[]") -> None:
        super().__init__()
        self.body = body
        self.aborted = False

    def error(self) -> QNetworkReply.NetworkError:
        if self.aborted:
            return QNetworkReply.NetworkError.OperationCanceledError
        return QNetworkReply.NetworkError.NoError

    def errorString(self) -> str:
        return "Fake request failure"

    def readAll(self) -> QByteArray:
        data = self.body
        self.body = b""
        return QByteArray(data)

    def bytesAvailable(self) -> int:
        return len(self.body)

    def abort(self) -> None:
        self.aborted = True
        self.finished.emit()


def client_with_reply(application: QApplication, reply: FakeReply) -> UpdateClient:
    client = UpdateClient("1.0.0", "stable", application)
    client.manager.get = Mock(return_value=reply)
    return client


def test_client_should_check_on_start_and_every_ten_minutes(application: QApplication) -> None:
    reply = FakeReply()
    client = client_with_reply(application, reply)
    result = Mock()
    client.checked.connect(result)
    client.start()
    assert client.timer.interval() == CHECK_INTERVAL_MS
    assert client.timer.isActive()
    client.check()
    client.manager.get.assert_called_once()
    reply.finished.emit()
    result.assert_called_once_with(None)
    next_reply = FakeReply()
    client.manager.get.return_value = next_reply
    client.timer.timeout.emit()
    assert client.manager.get.call_count == 2
    client.stop()


def test_client_should_make_no_requests_when_disabled(application: QApplication) -> None:
    client = client_with_reply(application, FakeReply())
    client.channel = "disabled"
    client.start()
    client.check()
    assert not client.timer.isActive()
    client.manager.get.assert_not_called()


def test_client_should_ignore_pending_reply_after_disabling(application: QApplication) -> None:
    reply = FakeReply()
    client = client_with_reply(application, reply)
    checked = Mock()
    failed = Mock()
    client.checked.connect(checked)
    client.failed.connect(failed)
    client.start()
    client.set_channel("disabled")
    reply.finished.emit()
    checked.assert_not_called()
    failed.assert_not_called()
    assert not client.timer.isActive()


def test_client_should_surface_invalid_metadata_without_crashing(application: QApplication) -> None:
    reply = FakeReply(b"not JSON")
    client = client_with_reply(application, reply)
    failed = Mock()
    client.failed.connect(failed)
    client.check()
    reply.finished.emit()
    failed.assert_called_once()
    assert client.reply is None


def test_client_should_follow_release_pages_before_selecting(application: QApplication) -> None:
    first = FakeReply(json.dumps([{"draft": True}] * 100).encode())
    second = FakeReply(
        json.dumps(
            [
                {
                    "draft": False,
                    "prerelease": False,
                    "tag_name": "v2.0.0",
                    "html_url": RELEASE_URL + "tag/v2.0.0",
                    "assets": [],
                }
            ]
        ).encode()
    )
    client = client_with_reply(application, first)
    client.manager.get = Mock(side_effect=[first, second])
    checked = Mock()
    client.checked.connect(checked)
    client.check()
    first.finished.emit()
    checked.assert_not_called()
    second.finished.emit()
    assert checked.call_args.args[0].version == "2.0.0"
    assert "page=2" in client.manager.get.call_args.args[0].url().toString()


@pytest.mark.parametrize("payload", [b"valid installer", b"corrupt", b"", b"valid installer extra"])
def test_download_should_only_publish_exact_hash_verified_file(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    expected = b"valid installer"
    digest = hashlib.sha256(expected).hexdigest()
    release = UpdateRelease(
        "2.0.0",
        RELEASE_URL + "tag/v2.0.0",
        False,
        RELEASE_URL + "download/v2.0.0/setup.exe",
        digest,
        len(expected),
    )
    reply = FakeReply(payload)
    client = client_with_reply(application, reply)
    monkeypatch.setattr(QStandardPaths, "writableLocation", lambda _: str(tmp_path))
    downloaded = Mock()
    failed = Mock()
    client.downloaded.connect(downloaded)
    client.failed.connect(failed)
    client.download(release)
    reply.finished.emit()
    target = tmp_path / "updates" / f"RocketLantern-{digest}-setup.exe"
    if payload == expected:
        downloaded.assert_called_once_with(str(target))
        failed.assert_not_called()
        assert target.read_bytes() == expected
    else:
        downloaded.assert_not_called()
        assert failed.called
        assert not target.exists()


def test_client_should_cancel_partial_download_when_closed(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QStandardPaths, "writableLocation", lambda _: str(tmp_path))
    reply = FakeReply(b"partial")
    client = client_with_reply(application, reply)
    downloaded = Mock()
    client.downloaded.connect(downloaded)
    client.download(
        UpdateRelease(
            "2.0.0",
            RELEASE_URL + "tag/v2.0.0",
            False,
            RELEASE_URL + "download/v2.0.0/setup.exe",
            "a" * 64,
            100,
        )
    )
    reply.readyRead.emit()
    client.stop()
    downloaded.assert_not_called()
    assert not list((tmp_path / "updates").iterdir())
