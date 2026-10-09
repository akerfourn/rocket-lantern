"""Bounded in-memory event journal with redacted player identities."""

import json
from datetime import datetime

from PySide6.QtWidgets import QApplication, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from rocket_lantern.i18n import DisplayText, render
from rocket_lantern.i18n import text as T
from rocket_lantern.protocol import normalize_message
from rocket_lantern.translated_widgets import TranslatedButton as QPushButton
from rocket_lantern.translated_widgets import TranslatedCheckBox as QCheckBox
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel

MAX_LOG_ENTRIES = 1000
MAX_ENTRY_LENGTH = 16_000
REDACTED_KEYS = {
    "name",
    "playername",
    "primaryid",
    "uniqueid",
    "playerid",
    "matchguid",
    "filename",
    "serverip",
    "servername",
    "teamname",
    "winner",
    "ip",
    "address",
    "password",
    "token",
    "authorization",
}


def redact(value: object, depth: int = 0) -> object:
    """Hide identifiers and names while preserving event fields and structure."""
    if depth > 30:
        return "[profondeur limitée]"
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key.casefold() in REDACTED_KEYS:
                sanitized[key] = "[masqué]"
            elif key.casefold() == "data" and not isinstance(item, dict):
                # Malformed or opaque payloads cannot safely be redacted field by field.
                sanitized[key] = "[Data non objet masqué]"
            else:
                sanitized[key] = redact(item, depth + 1)
        return sanitized
    if isinstance(value, list):
        return [redact(item, depth + 1) for item in value]
    return value


class LogPanel(QWidget):
    """Show every received message before domain filtering, without disk writes."""

    def __init__(self) -> None:
        super().__init__()
        self.received_count = 0
        layout = QVBoxLayout(self)
        self.summary = QLabel(T("0 messages reçus • aucune réception"))
        layout.addWidget(self.summary)
        controls = QHBoxLayout()
        self.follow = QCheckBox(T("Défilement automatique"))
        self.follow.setChecked(True)
        controls.addWidget(self.follow)
        clear = QPushButton(T("Effacer"))
        clear.clicked.connect(self.clear)
        controls.addWidget(clear)
        copy = QPushButton(T("Copier les logs"))
        copy.clicked.connect(self.copy)
        controls.addWidget(copy)
        layout.addLayout(controls)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(MAX_LOG_ENTRIES)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.text)
        hint = QLabel(
            T(
                "1 000 dernières entrées en mémoire, sans échantillonnage. Noms et "
                "identifiants masqués ; aucune sauvegarde automatique."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def record_payload(self, payload: str, observed_at: datetime) -> object:
        """Count and log incoming JSON, including messages the tracker will reject."""
        self.received_count += 1
        timestamp = observed_at.astimezone().strftime("%H:%M:%S.%f")[:-3]
        self.summary.setText(
            T(
                "{received_count} messages reçus • dernière réception {timestamp}",
                received_count=self.received_count,
                timestamp=timestamp,
            )
        )
        try:
            message = json.loads(payload)
        except json.JSONDecodeError as error:
            edges = T("message vide")
            if payload != "":
                edges = T(
                    "début U+{value:04X}, fin U+{value_2:04X}",
                    value=ord(payload[0]),
                    value_2=ord(payload[-1]),
                )
            details = T(
                "{msg} ; ligne {lineno}, colonne {colno}, position {pos} ; {count} "
                "caractères ; {edges}",
                msg=error.msg,
                lineno=error.lineno,
                colno=error.colno,
                pos=error.pos,
                count=len(payload),
                edges=edges,
            )
            self.append_entry(T("JSON invalide"), details, observed_at)
            raise ValueError(details) from None
        except (ValueError, RecursionError):
            self.append_entry(
                T("JSON invalide"), T("{count} caractères reçus", count=len(payload)), observed_at
            )
            raise ValueError(T("JSON invalide ou trop imbriqué.")) from None
        try:
            normalized = normalize_message(message)
        except ValueError:
            self._record_message(message, observed_at)
            raise
        self._record_message(normalized, observed_at)
        return normalized

    def _record_message(self, message: object, observed_at: datetime) -> None:
        serialized = json.dumps(redact(message), ensure_ascii=False, separators=(",", ":"))
        self.append_entry(T("Événement"), serialized, observed_at)

    def append_entry(
        self, category: DisplayText, details: DisplayText, observed_at: datetime | None = None
    ) -> None:
        """Append one bounded line, preserving the scroll position when paused."""
        if observed_at is None:
            observed_at = datetime.now().astimezone()
        timestamp = observed_at.astimezone().strftime("%H:%M:%S.%f")[:-3]
        category = render(category)
        details = render(details)
        details = details.replace("\r", "\\r").replace("\n", "\\n")
        if len(details) > MAX_ENTRY_LENGTH:
            details = details[:MAX_ENTRY_LENGTH] + render(T(" … [contenu tronqué]"))
        scrollbar = self.text.verticalScrollBar()
        position = scrollbar.value()
        self.text.appendPlainText(f"{timestamp} [{category}] {details}")
        if self.follow.isChecked():
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(position)

    def clear(self) -> None:
        """Clear the displayed journal while retaining the receive counter."""
        self.text.clear()

    def copy(self) -> None:
        """Copy the visible redacted journal at the user's request."""
        QApplication.clipboard().setText(self.text.toPlainText())
