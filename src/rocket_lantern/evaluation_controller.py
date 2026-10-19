"""Bind explicit match IDs to manual votes and the current/last match badge."""

import sqlite3
from datetime import UTC, datetime

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from rocket_lantern.labels import DEFAULT_LIST
from rocket_lantern.match_panel import MatchPanel
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchTracker


class EvaluationController(QObject):
    failed = Signal()

    def __init__(self, store: MatchStore, matches: MatchPanel, parent: QWidget) -> None:
        super().__init__(parent)
        self.store = store
        self.matches = matches
        self.guid = ""
        self.last_guid = ""
        matches.counters.evaluations.chosen.connect(self.save_label)
        matches.evaluation_changed.connect(self.save)
        matches.label_changed.connect(self.save_label)

    def _set_target(self, guid: str) -> None:
        if self.guid != guid:
            try:
                values = self.store.labels.choices(guid)
            except sqlite3.Error:
                self.failed.emit()
                guid = ""
                values = {}
            self.matches.counters.evaluations.set_match(guid, values)
            self.guid = guid

    def observe(self, tracker: MatchTracker, message: dict[str, object]) -> None:
        """Never move the vote target on late events from an older match."""
        if tracker.is_history_replay:
            self._set_target("")
            return
        event = message.get("Event")
        data = message.get("Data")
        if not isinstance(data, dict):
            return
        if event == "UpdateState":
            guid = data.get("MatchGuid")
            if not isinstance(guid, str) or not guid or tracker.team is None:
                self.last_guid = ""
                self._set_target("")
                return
            self.last_guid = guid
            self._set_target(guid)
        elif event == "MatchDestroyed" and tracker.match_id == "":
            self.show_last()

    def show_last(self) -> None:
        """Keep the last observed match editable after leaving or disconnecting."""
        self._set_target(self.last_guid)

    def reset_player(self) -> None:
        self.last_guid = ""
        self._set_target("")

    def save(self, guid: str, value: str) -> None:
        """Use the ID captured by the clicked menu, independent of current filters."""
        if guid == "":
            return
        try:
            self.store.set_evaluation(guid, value, datetime.now(UTC).isoformat())
        except (sqlite3.Error, ValueError):
            self.failed.emit()
            return
        self.matches.update_evaluation(guid, value)
        if guid == self.guid:
            self.matches.counters.evaluations.update_choice(guid, DEFAULT_LIST, value)

    def save_label(self, guid: str, list_id: str, value: str) -> None:
        if list_id == DEFAULT_LIST:
            self.save(guid, value)
            return
        if guid == "":
            return
        try:
            self.store.labels.choose(guid, list_id, value, datetime.now(UTC).isoformat())
        except (sqlite3.Error, ValueError):
            self.failed.emit()
            return
        self.matches.update_label(guid, list_id, value)
        if guid == self.guid:
            self.matches.counters.evaluations.update_choice(guid, list_id, value)

    def refresh(self) -> None:
        target = self.guid
        self.guid = ""
        self._set_target(target)

    def vote_current(self, value: str) -> None:
        """Keyboard shortcuts never target a selected historical row."""
        label = self.matches.catalog.labels.get(value)
        if label is not None:
            self.save_label(self.guid, label.list_id, value)
