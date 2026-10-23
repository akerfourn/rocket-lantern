"""Interpret Stats API events independently from Qt, storage and the clock."""

from dataclasses import dataclass
from typing import Literal

type Outcome = Literal["win", "loss", "unknown"]


@dataclass(frozen=True)
class Player:
    """Player identity and team supplied by the game."""

    primary_id: str
    name: str
    team: int


@dataclass(frozen=True)
class MatchResult:
    """Result observed for one selected player in one online or LAN match."""

    match_id: str
    player_id: str
    ended_at: str
    playlist: int | None
    outcome: Outcome


def parse_players(value: object) -> list[Player]:
    """Read valid player identities without retaining unrelated player data."""
    if not isinstance(value, list):
        return []
    players = []
    for item in value:
        if not isinstance(item, dict):
            continue
        primary_id = item.get("PrimaryId")
        name = item.get("Name")
        team = item.get("TeamNum")
        if not isinstance(primary_id, str) or primary_id == "":
            continue
        if not isinstance(name, str) or type(team) is not int or team not in (0, 1):
            continue
        players.append(Player(primary_id, name, team))
    return players


class MatchTracker:
    """Keep explicit match state for the selected player only."""

    def __init__(self, player_id: str = "") -> None:
        self.player_id = player_id
        self.players: list[Player] = []
        self.match_id = ""
        self.team: int | None = None
        # Last playing team in this match, frozen once its result is confirmed.
        self.last_team: int | None = None
        self.playlist: int | None = None
        self.is_history_replay = False
        self.is_finished = False
        self._has_live_state = False
        self.status = "En attente d’un événement UpdateState."

    def select_player(self, player_id: str) -> None:
        """Change selection; do not attribute an earlier match to a new player."""
        self._reset_match()
        self.player_id = player_id

    def handle(self, message: object, observed_at: str) -> list[MatchResult]:
        """Consume a decoded message using a caller-supplied observation time."""
        if not isinstance(message, dict):
            raise ValueError("Le message Stats API doit être un objet JSON.")
        event = message.get("Event")
        data = message.get("Data")
        if not isinstance(event, str) or not isinstance(data, dict):
            raise ValueError("Le message Stats API doit contenir Event et Data.")
        if event == "ReplayCreated":
            results = self.interrupt(observed_at)
            self.is_history_replay = True
            self.status = "Replay chargé : événements visibles, résultats non comptabilisés."
            return results
        if event == "MatchDestroyed":
            return self._destroy(data, observed_at)
        if self.is_history_replay:
            return []
        if event == "UpdateState":
            return self._update(data, observed_at)
        if event == "MatchEnded":
            if data.get("MatchGuid") != self.match_id:
                self.status = "Fin ignorée : aucune observation du même match."
                return []
            if self.last_team is None:
                self.status = "Fin ignorée : équipe du joueur sélectionné inconnue."
                return []
            return self._finish(data.get("WinnerTeamNum"), observed_at)
        return []

    def interrupt(self, observed_at: str) -> list[MatchResult]:
        """Record an unfinished match as unknown when observation stops."""
        results = self._finish(None, observed_at)
        self._reset_match()
        self.players = []
        self.is_history_replay = False
        self.status = "Suivi interrompu ; en attente d’un événement UpdateState."
        return results

    def _destroy(self, data: dict[str, object], observed_at: str) -> list[MatchResult]:
        if self.is_history_replay:
            self.is_history_replay = False
            self.players = []
            self.status = "Replay terminé ; en attente d’un match."
            return []
        if data.get("MatchGuid") != self.match_id:
            return []
        return self.interrupt(observed_at)

    def _update(self, data: dict[str, object], observed_at: str) -> list[MatchResult]:
        match_id = data.get("MatchGuid")
        game = data.get("Game")
        if not isinstance(game, dict):
            raise ValueError("UpdateState doit contenir un objet Game.")
        if not isinstance(match_id, str) or match_id == "":
            self.players = parse_players(data.get("Players"))
            self.team = None
            self.status = "Événement reçu sans MatchGuid : résultat non comptabilisable."
            return []
        # Some payloads include Frame / Elapsed outside playback; their presence is not enough.
        if (
            game.get("bReplay") is True
            and self.match_id == ""
            and ("Frame" in game or "Elapsed" in game)
        ):
            results = self.interrupt(observed_at)
            self.is_history_replay = True
            self.status = "Lecture de replay détectée : résultat non comptabilisé."
            return results
        results = []
        if match_id != self.match_id:
            results = self.interrupt(observed_at)
            self.match_id = match_id
        self.players = parse_players(data.get("Players"))
        is_replay = game.get("bReplay") is True
        # A spectator or absent player must not retain a previous team assignment.
        self.team = None
        for player in self.players:
            if player.primary_id == self.player_id:
                self.team = player.team
                if not self.is_finished:
                    self.last_team = player.team
        playlist = game.get("PlaylistId")
        if type(playlist) is int:
            self.playlist = playlist
        self.status = "Match suivi ; en attente du résultat."
        if self.player_id == "":
            self.status = "Événements reçus : sélectionne ton joueur pour compter les résultats."
        elif self.team is None:
            self.status = "Événements reçus : joueur sélectionné absent ou équipe inconnue."
        elif self.is_finished:
            self.status = "Résultat confirmé ; doublons ignorés."
        # A new casual lobby can expose the previous match's winner before kickoff.
        # Only a live false -> true transition can substitute for MatchEnded.
        if not is_replay and game.get("bHasWinner") is False:
            self._has_live_state = True
        if not is_replay and self._has_live_state and game.get("bHasWinner") is True:
            results.extend(self._finish(self._winner_team(game), observed_at))
        return results

    @staticmethod
    def _winner_team(game: dict[str, object]) -> int | None:
        teams = game.get("Teams")
        winner = game.get("Winner")
        if not isinstance(teams, list) or not isinstance(winner, str) or winner == "":
            return None
        for team in teams:
            if isinstance(team, dict) and team.get("Name") == winner:
                team_number = team.get("TeamNum")
                if type(team_number) is int and team_number in (0, 1):
                    return team_number
        return None

    def _finish(self, winner: object, observed_at: str) -> list[MatchResult]:
        if self.match_id == "" or self.last_team is None or self.is_finished:
            return []
        outcome: Outcome = "unknown"
        if type(winner) is int and winner in (0, 1):
            outcome = "loss"
            if winner == self.last_team:
                outcome = "win"
            self.is_finished = True
            self.status = "Résultat confirmé ; doublons ignorés."
        else:
            self.status = "Résultat inconnu : aucun vainqueur confirmé reçu."
        return [MatchResult(self.match_id, self.player_id, observed_at, self.playlist, outcome)]

    def _reset_match(self) -> None:
        self.match_id = ""
        self.team = None
        self.last_team = None
        self.playlist = None
        self.is_finished = False
        self._has_live_state = False
