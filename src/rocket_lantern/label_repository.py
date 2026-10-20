"""Versioned label catalog and one independently selected label per match/list."""

import json
import sqlite3

from rocket_lantern.labels import (
    DEFAULT_LIST,
    ICON_FAMILIES,
    SYMBOLS,
    Label,
    LabelList,
    default_labels,
    validate_color,
    validate_custom_id,
    validate_name,
)
from rocket_lantern.match_repository import match_key


def migrate_labels(connection: sqlite3.Connection) -> None:
    """Preserve catalogs and annotations while adding category icon families."""
    _migrate_legacy_labels(connection)
    if connection.execute("PRAGMA user_version").fetchone()[0] >= 5:
        return
    with connection:
        connection.execute("BEGIN")
        connection.execute(
            "ALTER TABLE label_lists ADD COLUMN family TEXT NOT NULL DEFAULT 'tag' "
            "CHECK (family IN ('tag', 'flag', 'shield'))"
        )
        connection.execute("PRAGMA user_version = 5")


def _migrate_legacy_labels(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA user_version").fetchone()[0] >= 4:
        return
    with connection:
        connection.execute("BEGIN")
        connection.execute(
            """CREATE TABLE label_lists (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL,
                position INTEGER NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE labels (
                id TEXT PRIMARY KEY, list_id TEXT NOT NULL REFERENCES label_lists(id),
                name TEXT NOT NULL, color TEXT NOT NULL, symbol TEXT NOT NULL,
                enabled INTEGER NOT NULL, position INTEGER NOT NULL, shortcut TEXT NOT NULL,
                UNIQUE(list_id, id)
            )"""
        )
        connection.execute(
            """CREATE TABLE match_labels (
                match_id INTEGER NOT NULL REFERENCES match_details(id),
                list_id TEXT NOT NULL REFERENCES label_lists(id), label_id TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY(match_id, list_id),
                FOREIGN KEY(list_id, label_id) REFERENCES labels(list_id, id)
            )"""
        )
        connection.execute(
            "INSERT INTO label_lists VALUES (?, ?, 1, 0)", (DEFAULT_LIST, "Suspicion de smurf")
        )
        shortcuts = _legacy_shortcuts(connection)
        for index, label in enumerate(default_labels()):
            connection.execute(
                "INSERT INTO labels VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    label.id,
                    label.list_id,
                    label.name,
                    label.color,
                    label.symbol,
                    1,
                    label.position,
                    shortcuts[index],
                ),
            )
        connection.execute(
            """INSERT INTO match_labels (match_id, list_id, label_id, updated_at)
               SELECT match_id, ?, evaluation, updated_at FROM match_evaluations""",
            (DEFAULT_LIST,),
        )
        connection.execute("DROP TABLE match_evaluations")
        connection.execute("PRAGMA user_version = 4")


def _legacy_shortcuts(connection: sqlite3.Connection) -> tuple[str, ...]:
    defaults = tuple(label.shortcut for label in default_labels())
    row = connection.execute(
        "SELECT value FROM settings WHERE key = 'evaluation_hotkeys'"
    ).fetchone()
    if row is None:
        return defaults
    if row[0] == "":
        return defaults
    try:
        values = json.loads(row[0])
        if not isinstance(values, list) or len(values) != 4:
            raise ValueError("Invalid legacy shortcuts")
        if not all(isinstance(value, str) for value in values):
            raise ValueError("Invalid legacy shortcuts")
        return tuple(values)
    except (TypeError, ValueError):
        connection.execute("UPDATE settings SET value='0' WHERE key='evaluation_hotkeys_enabled'")
        return defaults


class LabelRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def lists(self) -> tuple[LabelList, ...]:
        rows = self.connection.execute("SELECT * FROM label_lists ORDER BY position, id")
        return tuple(
            LabelList(row["id"], row["name"], bool(row["enabled"]), row["position"], row["family"])
            for row in rows
        )

    def labels(self) -> tuple[Label, ...]:
        rows = self.connection.execute("SELECT * FROM labels ORDER BY position, id")
        return tuple(
            Label(
                row["id"],
                row["list_id"],
                row["name"],
                row["color"],
                row["symbol"],
                bool(row["enabled"]),
                row["position"],
                row["shortcut"],
            )
            for row in rows
        )

    def save_list(self, item: LabelList) -> None:
        self._validate_list(item)
        with self.connection:
            self._write_list(item)

    def _validate_list(self, item: LabelList) -> None:
        validate_name(item.name)
        if item.family not in ICON_FAMILIES:
            raise ValueError("Unknown icon family")
        existing = self.connection.execute(
            "SELECT id FROM label_lists WHERE id = ?", (item.id,)
        ).fetchone()
        if existing is None:
            validate_custom_id(item.id)

    def _write_list(self, item: LabelList) -> None:
        self.connection.execute(
            """INSERT INTO label_lists (id, name, enabled, position, family)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                   enabled=excluded.enabled, position=excluded.position, family=excluded.family""",
            (item.id, item.name.strip(), int(item.enabled), item.position, item.family),
        )

    def save_label(self, item: Label) -> None:
        self._validate_label(item)
        with self.connection:
            self._write_label(item)

    def _validate_label(self, item: Label) -> None:
        validate_name(item.name)
        validate_color(item.color)
        if item.symbol not in SYMBOLS:
            raise ValueError("Unknown label symbol")
        existing = self.connection.execute(
            "SELECT list_id FROM labels WHERE id = ?", (item.id,)
        ).fetchone()
        if existing is None:
            validate_custom_id(item.id)
        elif existing[0] != item.list_id:
            raise ValueError("A label cannot move to another list")

    def _write_label(self, item: Label) -> None:
        self.connection.execute(
            """INSERT INTO labels VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, color=excluded.color,
                   symbol=excluded.symbol, enabled=excluded.enabled,
                   position=excluded.position, shortcut=excluded.shortcut""",
            (
                item.id,
                item.list_id,
                item.name.strip(),
                item.color,
                item.symbol,
                int(item.enabled),
                item.position,
                item.shortcut,
            ),
        )

    def save_catalog(self, groups: tuple[LabelList, ...], labels: tuple[Label, ...]) -> None:
        """Apply one editor draft atomically, without deleting historical definitions."""
        for group in groups:
            self._validate_list(group)
        for label in labels:
            self._validate_label(label)
        with self.connection:
            for group in groups:
                self._write_list(group)
            for label in labels:
                self._write_label(label)

    def choices(self, guid: str) -> dict[str, str]:
        rows = self.connection.execute(
            """SELECT l.list_id, l.label_id FROM match_labels l
               JOIN match_details d ON d.id=l.match_id WHERE d.guid=?""",
            (guid,),
        )
        return {row[0]: row[1] for row in rows}

    def choices_many(self, guids: tuple[str, ...]) -> dict[str, dict[str, str]]:
        if not guids:
            return {}
        placeholders = ",".join("?" for _ in guids)
        rows = self.connection.execute(
            """SELECT d.guid, l.list_id, l.label_id FROM match_labels l
               JOIN match_details d ON d.id=l.match_id WHERE d.guid IN ("""
            + placeholders
            + ")",
            guids,
        )
        result: dict[str, dict[str, str]] = {}
        for guid, list_id, label_id in rows:
            result.setdefault(guid, {})[list_id] = label_id
        return result

    def choose(self, guid: str, list_id: str, label_id: str, updated_at: str) -> None:
        if not isinstance(guid, str) or not guid.strip():
            raise ValueError("A match GUID is required")
        group = self.connection.execute(
            "SELECT enabled FROM label_lists WHERE id=?", (list_id,)
        ).fetchone()
        if group is None or not group[0]:
            raise ValueError("The list must exist and be enabled")
        definition = self.connection.execute(
            """SELECT l.enabled, g.enabled FROM labels l
               JOIN label_lists g ON g.id=l.list_id WHERE l.id=? AND l.list_id=?""",
            (label_id, list_id),
        ).fetchone()
        if label_id != "" and (definition is None or not all(definition)):
            raise ValueError("The label must belong to an enabled list and be enabled")
        with self.connection:
            match_id = match_key(self.connection, guid)
            if label_id == "":
                self.connection.execute(
                    "DELETE FROM match_labels WHERE match_id=? AND list_id=?", (match_id, list_id)
                )
                return
            self.connection.execute(
                """INSERT INTO match_labels VALUES (?, ?, ?, ?)
                   ON CONFLICT(match_id, list_id) DO UPDATE SET
                   label_id=excluded.label_id, updated_at=excluded.updated_at""",
                (match_id, list_id, label_id, updated_at),
            )
