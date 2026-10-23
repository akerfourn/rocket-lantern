"""Scoreboard filters follow stable IDs and the latest team assignment."""

from dataclasses import replace

from rocket_lantern.match_data import PlayerStats
from rocket_lantern.scoreboard_overlay_scope import ScoreboardScope, scoreboard_players


def roster() -> tuple[PlayerStats, ...]:
    return (
        PlayerStats("me", "Same name", 0),
        PlayerStats("mate", "Teammate", 0),
        PlayerStats("enemy", "Same name", 1),
    )


def test_all_players_should_include_both_teams_without_a_tracked_account() -> None:
    players = roster()

    assert scoreboard_players(players, "", ScoreboardScope.ALL) == players


def test_my_team_should_use_the_account_id_instead_of_identical_names() -> None:
    players = roster()

    assert scoreboard_players(players, "me", ScoreboardScope.TEAM) == players[:2]


def test_opponents_should_exclude_the_tracked_team() -> None:
    players = roster()

    assert scoreboard_players(players, "me", ScoreboardScope.OPPONENTS) == (players[2],)


def test_my_player_should_exclude_everyone_else() -> None:
    players = roster()

    assert scoreboard_players(players, "me", ScoreboardScope.PLAYER) == (players[0],)


def test_relative_filters_should_remain_empty_when_the_account_is_absent() -> None:
    for scope in (ScoreboardScope.TEAM, ScoreboardScope.OPPONENTS, ScoreboardScope.PLAYER):
        assert scoreboard_players(roster(), "missing", scope) == ()


def test_filters_should_use_the_latest_team_when_a_private_match_player_switches_sides() -> None:
    players = roster()
    switched = (replace(players[0], team=1), *players[1:])

    assert scoreboard_players(switched, "me", ScoreboardScope.TEAM) == (switched[0], switched[2])
    assert scoreboard_players(switched, "me", ScoreboardScope.OPPONENTS) == (switched[1],)
    assert players[0].team == 0, "Filtering must not mutate match observations"
