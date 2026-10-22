"""Refresh live recognition on roster changes, not on every telemetry packet."""

import sqlite3

from PySide6.QtCore import QObject, Signal

from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.storage import MatchStore


class PlayerEncounterController(QObject):
    """Keep a bounded lookup for the live roster, independent of history filters."""

    failed = Signal()

    def __init__(self, store: MatchStore, panel: LiveMatchPanel, parent: QObject) -> None:
        super().__init__(parent)
        self.store = store
        self.panel = panel
        self._context: tuple[str, str, tuple[str, ...]] | None = None
        panel.state_changed.connect(self.update)

    def refresh(self) -> None:
        """Re-evaluate encounters after saved results or an explicit session split."""
        self._context = None
        self.update()

    def update(self) -> None:
        snapshot = self.panel.state.snapshot
        if snapshot is None:
            self._context = None
            self.panel.players.set_encounters({})
            return
        primary_ids = tuple(sorted(snapshot.players))
        context = (snapshot.guid, self.panel.player_id, primary_ids)
        if context == self._context:
            return
        self._context = context
        try:
            encounters = self.store.player_encounters(
                primary_ids,
                player_id=self.panel.player_id,
                exclude_match=snapshot.guid,
                observed_at=snapshot.observed_at,
            )
        except sqlite3.Error:
            self.panel.players.set_encounters({})
            self.failed.emit()
            return
        self.panel.players.set_encounters(encounters)
