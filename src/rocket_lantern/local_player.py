"""Read only primary-account login events from Rocket League's current log."""

import os
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

MAX_READ_BYTES = 256 * 1024
MAX_LINE_BYTES = 4096
LOGIN_EVENT = re.compile(
    r"^\[\d+\.\d+\]\s+Party: HandleLocalPlayerLoginStatusChanged "
    r"PlayerName=(.*?) PlayerID=((?:Steam|Epic|Unknown)\|[A-Za-z0-9]+\|0) "
    r"LoginStatus=(LS_\w+) IsPrimary=True(?:\s|$)"
)


@dataclass(frozen=True)
class LocalPlayer:
    primary_id: str
    name: str


def parse_login(line: str) -> tuple[bool, LocalPlayer | None]:
    """Distinguish an explicit primary logout from unrelated log messages."""
    match = LOGIN_EVENT.match(line)
    if match is None:
        return False, None
    name, primary_id, status = match.groups()
    if status != "LS_LoggedIn" or primary_id.startswith("Unknown|"):
        return True, None
    return True, LocalPlayer(primary_id, name)


class LocalPlayerLog:
    """Follow bounded chunks without retaining logs, credentials or an open file handle."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.reset()

    def reset(self) -> None:
        self.player: LocalPlayer | None = None
        self.ready = False
        self._file_id: tuple[int, int] | None = None
        self._offset = 0
        self._modified = 0
        self._prefix_digest = b""
        self._prefix_size = 0
        self._pending = b""
        self._discard_line = False

    def read(self, not_before: float = 0) -> LocalPlayer | None:
        """Read one bounded chunk; ready marks when all current events were examined."""
        try:
            with self.path.open("rb") as stream:
                status = os.fstat(stream.fileno())
                if status.st_mtime < not_before:
                    self.reset()
                    self.ready = True
                    return None
                file_id = (status.st_dev, status.st_ino)
                prefix = stream.read(self._prefix_size)
                if (
                    file_id != self._file_id
                    or status.st_size < self._offset
                    or (self._prefix_size > 0 and sha256(prefix).digest() != self._prefix_digest)
                    or (status.st_size == self._offset and status.st_mtime_ns != self._modified)
                ):
                    self.reset()
                self._file_id = file_id
                if self._prefix_size == 0:
                    stream.seek(0)
                    prefix = stream.read(256)
                    self._prefix_size = len(prefix)
                    self._prefix_digest = sha256(prefix).digest()
                stream.seek(self._offset)
                chunk = stream.read(MAX_READ_BYTES)
        except FileNotFoundError:
            self.reset()
            self.ready = True
            return None
        self._offset += len(chunk)
        self._modified = status.st_mtime_ns
        self._consume(chunk)
        self.ready = self._offset >= status.st_size
        return self.player

    def _consume(self, chunk: bytes) -> None:
        lines = (self._pending + chunk).split(b"\n")
        self._pending = lines.pop()
        for line in lines:
            if not self._discard_line and len(line) <= MAX_LINE_BYTES:
                relevant, player = parse_login(line.decode("utf-8", errors="replace").rstrip("\r"))
                if relevant:
                    self.player = player
            self._discard_line = False
        if len(self._pending) > MAX_LINE_BYTES:
            self._pending = b""
            self._discard_line = True
