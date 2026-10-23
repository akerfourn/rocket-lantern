"""Select live scoreboard participants by stable identity and the tracked account's team."""

from collections.abc import Sequence
from enum import StrEnum

from rocket_lantern.match_data import PlayerStats


class ScoreboardScope(StrEnum):
    ALL = "all"
    TEAM = "team"
    OPPONENTS = "opponents"
    PLAYER = "player"


def scoreboard_players(
    players: Sequence[PlayerStats], player_id: str, scope: ScoreboardScope
) -> tuple[PlayerStats, ...]:
    """Never guess a relative team when the tracked account is missing from the roster."""
    if scope == ScoreboardScope.ALL:
        return tuple(players)
    selected = None
    for player in players:
        if player.primary_id == player_id:
            selected = player
            break
    if selected is None or selected.team not in (0, 1):
        return ()
    if scope == ScoreboardScope.PLAYER:
        return (selected,)
    if scope == ScoreboardScope.TEAM:
        return tuple(player for player in players if player.team == selected.team)
    return tuple(player for player in players if player.team != selected.team)
