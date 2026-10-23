"""Suppress identical, closely repeated impacts in the live counter only."""

from dataclasses import dataclass

from rocket_lantern.event_data import number
from rocket_lantern.event_deduplication import RecentEventDeduplicator


@dataclass(frozen=True)
class PostImpact:
    """Compare exact API measurements without rounding world coordinates."""

    player_id: str
    team: int
    position: tuple[float, float, float]
    ball_speed: float | None
    impact_force: float | None
    last_touch_speed: float | None


def impact_signature(data: dict[str, object], player_id: str, team: int) -> PostImpact | None:
    """Leave incomplete XYZ positions unmerged rather than guessing an impact identity."""
    location = data.get("BallLocation")
    if not isinstance(location, dict):
        return None
    x = number(location.get("X"))
    y = number(location.get("Y"))
    z = number(location.get("Z"))
    if x is None or y is None or z is None:
        return None
    touch_speed = None
    last_touch = data.get("BallLastTouch")
    if isinstance(last_touch, dict):
        touch_speed = number(last_touch.get("Speed"))
    return PostImpact(
        player_id,
        team,
        (x, y, z),
        number(data.get("BallSpeed")),
        number(data.get("ImpactForce")),
        touch_speed,
    )


class PostHitDeduplicator:
    """Keep at most 32 recent impacts; never retain a match-long event history."""

    def __init__(self) -> None:
        self._duplicates = RecentEventDeduplicator()

    def clear(self) -> None:
        """Discard identities at a match or connection boundary."""
        self._duplicates.clear()

    def is_duplicate(
        self, data: dict[str, object], player_id: str, team: int, observed_at: str
    ) -> bool:
        """Remember this impact and recognize exact repeats within the short rolling window."""
        impact = impact_signature(data, player_id, team)
        return self._duplicates.is_duplicate(impact, observed_at)
