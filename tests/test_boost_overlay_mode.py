"""Private-only is an explicit allowlist, not the absence of a ranked playlist."""

import pytest

from rocket_lantern.boost_overlay_mode import BoostOverlayMode


@pytest.mark.parametrize("playlist", [6, 7, 8, 9, 19, 20, 21, 24, 73])
def test_private_mode_should_allow_private_local_and_training_playlists(playlist: int) -> None:
    assert BoostOverlayMode.PRIVATE.allows(playlist)
    assert not BoostOverlayMode.NEVER.allows(playlist)
    assert BoostOverlayMode.ALL.allows(playlist)


@pytest.mark.parametrize("playlist", [None, -2, 0, 1, 2, 3, 4, 11, 13, 16, 22, 34, 54, 999])
def test_private_mode_should_exclude_matchmaking_tournaments_and_unknown_playlists(
    playlist: int | None,
) -> None:
    assert not BoostOverlayMode.PRIVATE.allows(playlist)
    assert not BoostOverlayMode.NEVER.allows(playlist)
    assert BoostOverlayMode.ALL.allows(playlist)
