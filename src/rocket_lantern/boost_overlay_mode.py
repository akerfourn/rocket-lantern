"""Restrict the boost HUD to explicitly recognized non-matchmade playlists."""

from enum import StrEnum

# Numeric reference only; no BakkesMod dependency or game hooks are used:
# https://bakkesplugins.com/wiki/bakkesmod-sdk/code-snippets/playlist-id
# Custom tournaments are excluded: their entrants may be strangers.
PRIVATE_PLAYLISTS = frozenset({6, 7, 8, 9, 19, 20, 21, 24, 73})


class BoostOverlayMode(StrEnum):
    NEVER = "never"
    PRIVATE = "private"
    ALL = "all"

    def allows(self, playlist: int | None) -> bool:
        """Fail closed for unknown modes unless all matches were explicitly selected."""
        if self == BoostOverlayMode.ALL:
            return True
        if self == BoostOverlayMode.PRIVATE:
            return type(playlist) is int and playlist in PRIVATE_PLAYLISTS
        return False
