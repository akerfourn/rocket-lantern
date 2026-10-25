"""Persistent rules and deterministic live event matching, without audio or a clock."""

import json
from dataclasses import replace

import pytest

from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.sound_alert_engine import (
    SAVE_DELAY,
    AlertContext,
    SoundAlertEngine,
    matches_scope,
)
from rocket_lantern.sound_alerts import (
    PlayerScope,
    SoundAlertConfig,
    SoundAlertMode,
    SoundRule,
    SoundTrigger,
    parse_sound_config,
)


def rule(trigger: SoundTrigger, scope: PlayerScope = PlayerScope.SELF, index: int = 1) -> SoundRule:
    return SoundRule(f"00000000-0000-0000-0000-{index:012d}", trigger, scope)


def context(
    *, guid: str = "match", playlist: int | None = 2, player_id: str = "me"
) -> AlertContext:
    snapshot = MatchSnapshot(guid, "2026-10-25T19:00:00+00:00", playlist=playlist, time_seconds=150)
    for player in (
        PlayerStats("me", "Same", 0, saves=1),
        PlayerStats("mate", "Mate", 0, saves=1),
        PlayerStats("enemy", "Same", 1, saves=1),
        PlayerStats("enemy2", "Other", 1, saves=1),
    ):
        snapshot.players[player.primary_id] = player
    snapshot.shortcuts = {(0, 1): "me", (0, 2): "mate", (1, 1): "enemy", (1, 2): "enemy2"}
    return AlertContext(snapshot, player_id)


def stat(
    name: object, actor: object = "me", target: object = "enemy", **extra: object
) -> dict[str, object]:
    return {
        "Event": "StatfeedEvent",
        "Data": {
            "MatchGuid": "match",
            "EventName": name,
            "MainTarget": {"PrimaryId": actor},
            "SecondaryTarget": {"PrimaryId": target},
            **extra,
        },
    }


def engine(*rules: SoundRule, mode: SoundAlertMode = SoundAlertMode.ALL) -> SoundAlertEngine:
    return SoundAlertEngine(SoundAlertConfig(mode, 70, tuple(rules)))


def test_sound_config_should_round_trip_and_default_to_disabled() -> None:
    config = SoundAlertConfig(rules=(rule(SoundTrigger.ASSIST),))

    restored = parse_sound_config(config.serialize())

    assert restored == config
    assert restored.mode == SoundAlertMode.NEVER
    assert restored.rules[0].id == config.rules[0].id


@pytest.mark.parametrize("mutation", ["version", "volume", "duplicate", "file_path", "alias"])
def test_sound_config_should_reject_malformed_or_unsafe_preferences(mutation: str) -> None:
    data = json.loads(SoundAlertConfig(rules=(rule(SoundTrigger.GOAL),)).serialize())
    if mutation == "version":
        data["version"] = 2
    elif mutation == "volume":
        data["volume"] = True
    elif mutation == "duplicate":
        data["rules"] *= 2
    elif mutation == "file_path":
        data["rules"][0]["sound"] = {"kind": "file", "value": "../other.mp3"}
    else:
        data["rules"][0]["sound"]["value"] = "ArbitraryRegistryKey"

    with pytest.raises(ValueError):
        parse_sound_config(json.dumps(data))


@pytest.mark.parametrize(
    "playlist, allowed",
    [(6, True), (24, True), (73, True), (2, False), (11, False), (34, False), (None, False)],
)
def test_private_audio_mode_should_exclude_matchmaking_and_unknown_playlists(
    playlist: int | None, allowed: bool
) -> None:
    assert SoundAlertMode.PRIVATE.allows(playlist) == allowed


def test_assist_should_follow_primary_id_and_not_a_matching_player_name() -> None:
    selected = rule(SoundTrigger.ASSIST)
    alerts = engine(selected)

    assert alerts.observe(stat("Assist", "enemy"), context(), 0) == ()
    assert alerts.observe(stat("Assist", "me"), context(), 0) == (selected,)


def test_demolished_should_filter_the_victim_instead_of_the_attacker() -> None:
    teammate = rule(SoundTrigger.DEMOLISHED, PlayerScope.TEAMMATES)
    own_demo = rule(SoundTrigger.DEMOLISH, PlayerScope.SELF, 2)
    alerts = engine(teammate, own_demo)

    assert alerts.observe(stat("Demolish", "enemy", "mate"), context(), 0) == (teammate,)
    assert alerts.observe(stat("Demolish", "enemy", "me"), context(), 1) == ()
    assert alerts.observe(stat("Demolish", "me", "enemy"), context(), 2) == (own_demo,)


def test_different_matching_rules_should_request_overlapping_sounds_for_the_same_event() -> None:
    author = rule(SoundTrigger.DEMOLISH)
    victim = rule(SoundTrigger.DEMOLISHED, PlayerScope.OPPONENTS, 2)

    assert engine(author, victim).observe(stat("Demolish"), context(), 0) == (author, victim)


def test_player_scopes_should_distinguish_myself_from_teammates_and_the_entire_team() -> None:
    current = context()
    players = current.snapshot.players
    expected = {
        PlayerScope.SELF: {"me"},
        PlayerScope.TEAMMATES: {"mate"},
        PlayerScope.TEAM: {"me", "mate"},
        PlayerScope.OPPONENTS: {"enemy", "enemy2"},
        PlayerScope.EVERYONE: set(players),
    }
    for scope, identities in expected.items():
        assert {
            key for key, value in players.items() if matches_scope(scope, value, current)
        } == identities


def test_missing_local_account_should_not_guess_a_team_but_allow_everyone_scope() -> None:
    relative = rule(SoundTrigger.ASSIST, PlayerScope.TEAM)
    anyone = rule(SoundTrigger.ASSIST, PlayerScope.EVERYONE, 2)

    assert engine(relative, anyone).observe(stat("Assist"), context(player_id="missing"), 0) == (
        anyone,
    )


def test_event_subject_should_resolve_current_shortcuts_but_never_names_alone() -> None:
    selected = rule(SoundTrigger.ASSIST)
    alerts = engine(selected)
    message = stat("Assist")
    message["Data"]["MainTarget"] = {"Name": "Same"}
    assert alerts.observe(message, context(), 0) == ()
    message["Data"]["MainTarget"] = {"Name": "Same", "TeamNum": 0, "Shortcut": 1}
    assert alerts.observe(message, context(), 0) == (selected,)


def test_goal_should_use_goal_scored_without_also_playing_statfeed_goal() -> None:
    selected = rule(SoundTrigger.GOAL)
    alerts = engine(selected)
    goal = {"Event": "GoalScored", "Data": {"MatchGuid": "match", "Scorer": {"PrimaryId": "me"}}}

    assert alerts.observe(goal, context(), 0) == (selected,)
    assert alerts.observe(stat("Goal"), context(), 0) == ()


def test_duplicate_notifications_should_not_suppress_distinct_actors_or_later_actions() -> None:
    selected = rule(SoundTrigger.ASSIST, PlayerScope.EVERYONE)
    alerts = engine(selected)

    assert alerts.observe(stat("Assist"), context(), 0) == (selected,)
    assert alerts.observe(stat("Assist"), context(), 0.05) == ()
    assert alerts.observe(stat("Assist", "mate"), context(), 0.05) == (selected,)
    assert alerts.observe(stat("Assist"), context(), 1) == (selected,)


@pytest.mark.parametrize("order", [("Save", "EpicSave"), ("EpicSave", "Save")])
def test_epic_save_should_take_priority_over_a_general_save_without_double_sound(
    order: tuple[str, str],
) -> None:
    normal = rule(SoundTrigger.SAVE)
    epic = rule(SoundTrigger.EPIC_SAVE, index=2)
    alerts = engine(normal, epic)
    output = []
    output.extend(alerts.observe(stat(order[0]), context(), 0))
    output.extend(alerts.observe(stat(order[1]), context(), 0.03))
    output.extend(alerts.flush(context(), 1))

    assert output == [epic]
    assert not alerts.pending


def test_general_save_should_cover_epic_saves_when_no_specific_rule_matches() -> None:
    normal = rule(SoundTrigger.SAVE)
    other_epic = rule(SoundTrigger.EPIC_SAVE, PlayerScope.OPPONENTS, 2)

    assert engine(normal, other_epic).observe(stat("EpicSave"), context(), 0) == (normal,)


def test_normal_save_should_play_after_the_coalescing_window_without_blocking_other_events() -> (
    None
):
    normal = rule(SoundTrigger.SAVE)
    assist = rule(SoundTrigger.ASSIST, index=2)
    alerts = engine(normal, assist)

    assert alerts.observe(stat("Save"), context(), 0) == ()
    assert alerts.pending
    assert alerts.flush(context(), SAVE_DELAY / 2) == ()
    assert alerts.observe(stat("Assist"), context(), 0.04) == (assist,)
    assert alerts.flush(context(), SAVE_DELAY + 0.01) == (normal,)


def test_epic_save_for_another_player_should_not_cancel_a_pending_save() -> None:
    normal = rule(SoundTrigger.SAVE, PlayerScope.EVERYONE)
    alerts = engine(normal)
    alerts.observe(stat("Save"), context(), 0)

    assert alerts.observe(stat("EpicSave", "mate"), context(), 0.02) == (normal,)
    assert alerts.flush(context(), 1) == (normal,)


def test_disabled_private_and_replay_modes_should_never_create_requests() -> None:
    selected = rule(SoundTrigger.ASSIST)
    assert engine(selected, mode=SoundAlertMode.NEVER).observe(stat("Assist"), context(), 0) == ()
    assert engine(selected, mode=SoundAlertMode.PRIVATE).observe(stat("Assist"), context(), 0) == ()
    assert engine(selected).observe(stat("Assist"), replace(context(), replay=True), 0) == ()
    assert engine(selected).observe(stat("Assist", bReplay=True), context(), 0) == ()
    assert engine(replace(selected, enabled=False)).observe(stat("Assist"), context(), 0) == ()
    assert engine(selected, mode=SoundAlertMode.PRIVATE).observe(
        stat("Assist"), context(playlist=6), 0
    ) == (selected,)


def test_invalid_events_should_be_ignored_without_fabricating_subjects() -> None:
    alerts = engine(rule(SoundTrigger.ASSIST, PlayerScope.EVERYONE))
    for message in (
        stat(["Assist"]),
        stat("Assist", "absent"),
        {"Event": "StatfeedEvent", "Data": None},
        {"Event": "StatfeedEvent", "Data": {"MatchGuid": "another", "EventName": "Assist"}},
    ):
        assert alerts.observe(message, context(), 0) == ()


def test_match_end_should_remain_silent_after_rule_edits_and_account_changes() -> None:
    selected = rule(SoundTrigger.ASSIST)
    alerts = engine(selected)
    alerts.observe({"Event": "MatchEnded", "Data": {"MatchGuid": "match"}}, context(), 0)
    alerts.configure(SoundAlertConfig(SoundAlertMode.ALL, 50, (selected,)))

    assert alerts.observe(stat("Assist"), context(), 1) == ()
    assert alerts.observe(stat("Assist", "mate"), context(player_id="mate"), 2) == ()


def test_pending_saves_should_be_discarded_on_disconnect_replay_or_account_switch() -> None:
    for updated in (
        AlertContext(None, "me"),
        replace(context(), replay=True),
        context(player_id="mate"),
    ):
        alerts = engine(rule(SoundTrigger.SAVE))
        alerts.observe(stat("Save"), context(), 0)

        assert alerts.flush(updated, 1) == ()
        assert not alerts.pending
