"""Locally known players and explicitly bookmarked accounts, independent of tracking."""

import json
import logging

from PySide6.QtCore import QObject, Signal

from rocket_lantern.local_player import LocalPlayer
from rocket_lantern.storage import MatchStore

LOGGER = logging.getLogger(__name__)


class PlayerFavorites(QObject):
    changed = Signal()

    def __init__(self, store: MatchStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.known: dict[str, str] = {}
        self.favorites = self._load_favorites()
        self.refresh_known()

    def _load_favorites(self) -> dict[str, str]:
        saved = self.store.setting("favorite_players")
        if saved == "":
            return {}
        try:
            values = json.loads(saved)
            if isinstance(values, dict) and all(
                isinstance(key, str) and key and isinstance(name, str) and name
                for key, name in values.items()
            ):
                return values
        except ValueError:
            pass
        LOGGER.warning("Ignoring invalid saved player favorites")
        return {}

    def refresh_known(self) -> None:
        self.known.update(self.favorites)
        for player in self.store.known_players():
            self.known[player["primary_id"]] = player["name"]
        primary_id = self.store.setting("player_id")
        name = self.store.setting("player_name")
        if primary_id:
            self.known[primary_id] = name or primary_id

    def observe(self, players: tuple[LocalPlayer, ...]) -> None:
        for player in players:
            self.known[player.primary_id] = player.name or player.primary_id

    def players(self, favorites_only: bool = False) -> tuple[LocalPlayer, ...]:
        names = self.known
        if favorites_only:
            names = {key: self.known.get(key, name) for key, name in self.favorites.items()}
        return tuple(
            LocalPlayer(primary_id, name)
            for primary_id, name in sorted(
                names.items(),
                key=lambda item: (item[0] not in self.favorites, item[1].casefold(), item[0]),
            )
        )

    def set_favorite(self, primary_id: str, name: str, favorite: bool) -> None:
        """Commit preferences before notifying widgets; failed writes leave them unchanged."""
        if not primary_id or not name:
            raise ValueError("A player identifier and name are required")
        updated = dict(self.favorites)
        if favorite:
            updated[primary_id] = name
        else:
            updated.pop(primary_id, None)
        if updated == self.favorites:
            return
        self.store.set_setting("favorite_players", json.dumps(updated, ensure_ascii=True))
        self.favorites = updated
        self.known[primary_id] = name
        self.changed.emit()
