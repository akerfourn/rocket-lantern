"""Playlist labels retain the API ID and avoid guesses for new playlists."""

import pytest

from rl_winloose.playlists import playlist_label


@pytest.mark.parametrize(
    "playlist_id, expected",
    [(11, "2v2 classé"), (3, "3v3 occasionnel"), (6, "Match privé")],
)
def test_playlist_should_show_session_type_when_id_is_known(
    playlist_id: int, expected: str
) -> None:
    label = playlist_label(playlist_id)

    assert expected in label
    assert f"ID {playlist_id}" in label


def test_playlist_should_keep_unknown_id_when_no_mapping_exists() -> None:
    assert playlist_label(9999) == "Playlist inconnue (ID 9999)"
    assert playlist_label(None) == "Type de partie inconnu"
