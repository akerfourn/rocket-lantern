"""Readable labels for the PlaylistId supplied by the official Stats API."""

from rocket_lantern.i18n import Text, render, text

# Numeric reference only; no BakkesMod dependency or connection is used:
# https://bakkesplugins.com/wiki/bakkesmod-sdk/code-snippets/playlist-id
PLAYLIST_NAMES: dict[int, str] = {
    0: "Occasionnel",
    1: "1v1 occasionnel",
    2: "2v2 occasionnel",
    3: "3v3 occasionnel",
    4: "4v4 occasionnel",
    6: "Match privé",
    7: "Saison hors ligne",
    8: "Exhibition",
    9: "Entraînement",
    10: "1v1 classé",
    11: "2v2 classé",
    13: "3v3 classé",
    15: "Snow Day occasionnel",
    16: "Rocket Labs",
    17: "Hoops occasionnel",
    18: "Rumble occasionnel",
    19: "Workshop",
    20: "Éditeur d’entraînement",
    21: "Entraînement personnalisé",
    22: "Tournoi personnalisé",
    23: "Dropshot occasionnel",
    24: "Match local / LAN",
    27: "Hoops classé",
    28: "Rumble classé",
    29: "Dropshot classé",
    30: "Snow Day classé",
    34: "Tournoi automatique",
    35: "Rocket Labs",
    38: "Heatseeker",
    43: "Heatseeker 2v2",
    54: "Knockout",
    73: "Entraînement libre en ligne",
}


def playlist_label(playlist_id: int | None) -> str:
    """Keep unknown IDs visible rather than guessing their game mode."""
    return render(playlist_text(playlist_id))


def playlist_text(playlist_id: int | None) -> Text:
    """Retain the playlist source so existing widgets can change language."""
    if playlist_id is None:
        return text("Type de partie inconnu")
    name = PLAYLIST_NAMES.get(playlist_id)
    if name is None:
        return text("Playlist inconnue (ID {playlist_id})", playlist_id=playlist_id)
    return text("{name} (ID {playlist_id})", name=text(name), playlist_id=playlist_id)
