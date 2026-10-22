"""Recognition uses saved identities and stable sessions, never names or the live match."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from rocket_lantern.match_data import MatchSnapshot, PlayerStats
from rocket_lantern.match_repository import player_key
from rocket_lantern.player_encounters import EncounterScope
from rocket_lantern.storage import MatchStore
from rocket_lantern.tracker import MatchResult


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    yield database
    database.close()


def save_encounter(
    store: MatchStore,
    guid: str,
    observed_at: str,
    participants: tuple[str, ...],
    owner: str = "me",
) -> None:
    snapshot = MatchSnapshot(guid, observed_at)
    snapshot.players = {
        primary_id: PlayerStats(primary_id, "Same display name", 0) for primary_id in participants
    }
    store.save_details(snapshot)
    store.save(MatchResult(guid, owner, observed_at, 11, "win"))


def test_encounters_should_prioritize_current_session_across_all_saved_accounts(
    store: MatchStore,
) -> None:
    save_encounter(
        store, "old", "2026-10-04T18:00:00+00:00", ("old", "both"), owner="other-account"
    )
    save_encounter(store, "recent", "2026-10-04T20:00:00+00:00", ("me", "recent", "both"))
    changes = store.connection.total_changes

    encounters = store.player_encounters(
        ("me", "old", "both", "recent", "new", "recent", ""),
        player_id="me",
        exclude_match="live",
        observed_at="2026-10-04T20:10:00+00:00",
    )

    assert encounters == {
        "old": EncounterScope.HISTORY,
        "both": EncounterScope.SESSION,
        "recent": EncounterScope.SESSION,
    }
    assert store.connection.total_changes == changes, "Recognition must not write match data"


def test_encounters_should_exclude_current_match_even_after_its_result_is_saved(
    store: MatchStore,
) -> None:
    save_encounter(store, "live", "2026-10-04T20:00:00+00:00", ("me", "first-encounter"))

    assert (
        store.player_encounters(
            ("me", "first-encounter"),
            player_id="me",
            exclude_match="live",
            observed_at="2026-10-04T20:01:00+00:00",
        )
        == {}
    )


def test_encounters_should_use_ids_not_display_names_or_favorite_identities(
    store: MatchStore,
) -> None:
    save_encounter(store, "old", "2026-10-04T20:00:00+00:00", ("known-id",))
    with store.connection:
        player_key(store.connection, "identity-without-a-match")

    encounters = store.player_encounters(
        ("known-id", "different-id-same-name", "identity-without-a-match"),
        player_id="me",
        exclude_match="live",
        observed_at="2026-10-04T20:10:00+00:00",
    )

    assert encounters == {"known-id": EncounterScope.SESSION}


def test_encounters_should_show_history_after_session_expiry_without_creating_a_session(
    store: MatchStore,
) -> None:
    save_encounter(store, "old", "2026-10-04T20:00:00+00:00", ("known",))

    encounters = store.player_encounters(
        ("known",),
        player_id="me",
        exclude_match="live",
        observed_at="2026-10-04T21:00:00+00:00",
    )

    assert encounters == {"known": EncounterScope.HISTORY}
    assert len(store.sessions("me")) == 1


def test_encounters_should_use_the_tracked_accounts_session_after_a_manual_split(
    store: MatchStore,
) -> None:
    save_encounter(store, "old", "2026-10-04T20:00:00+00:00", ("known",))
    store.start_session("me", "2026-10-04T20:02:00+00:00")

    encounters = store.player_encounters(
        ("known",),
        player_id="me",
        exclude_match="live",
        observed_at="2026-10-04T20:03:00+00:00",
    )

    assert encounters == {"known": EncounterScope.HISTORY}


def test_encounters_should_include_recorded_participants_without_requiring_a_win_loss_result(
    store: MatchStore,
) -> None:
    snapshot = MatchSnapshot("interrupted", "2026-10-04T20:00:00+00:00")
    snapshot.players["known"] = PlayerStats("known", "Old nickname", 1)
    store.save_details(snapshot)

    encounters = store.player_encounters(
        ("known",),
        player_id="new-account",
        exclude_match="live",
        observed_at="2026-10-04T20:10:00+00:00",
    )

    assert encounters == {"known": EncounterScope.HISTORY}
    assert store.sessions("new-account") == []


def test_encounters_should_handle_an_empty_roster_without_loading_saved_players(
    store: MatchStore,
) -> None:
    save_encounter(store, "old", "2026-10-04T20:00:00+00:00", ("known",))
    queries = []
    store.connection.set_trace_callback(queries.append)

    encounters = store.player_encounters(
        (), player_id="me", exclude_match="live", observed_at="2026-10-04T20:10:00+00:00"
    )

    assert encounters == {}
    assert not any("match_players" in query for query in queries)


def test_encounter_index_should_survive_reopening_an_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "matches.sqlite3"
    for _ in range(2):
        database = MatchStore(path)
        try:
            indexes = database.connection.execute("PRAGMA index_list(match_players)").fetchall()
            assert "match_players_identity" in {row["name"] for row in indexes}
            assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            database.close()
