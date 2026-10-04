"""Storage contracts with isolated in-memory databases."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from rl_winloose.storage import MatchStore, Summary
from rl_winloose.tracker import MatchResult, Outcome


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    yield database
    database.close()


def result(outcome: Outcome, match_id: str = "match-1", player_id: str = "test") -> MatchResult:
    """Build an explicit deterministic database fixture."""
    return MatchResult(match_id, player_id, "2026-10-02T12:00:00+00:00", 11, outcome)


def test_store_should_count_once_when_duplicate_result_arrives(store: MatchStore) -> None:
    store.save(result("win"))
    store.save(result("win"))

    assert store.summary("test") == Summary(1, 0, 0)
    assert len(store.history("test")) == 1


def test_store_should_replace_unknown_when_confirmed_result_arrives(store: MatchStore) -> None:
    store.save(result("unknown"))
    store.save(result("loss"))
    store.save(result("unknown"))

    assert store.summary("test") == Summary(0, 1, 0)


def test_summary_should_exclude_unknown_when_calculating_rate(store: MatchStore) -> None:
    store.save(result("win", "one"))
    store.save(result("loss", "two"))
    store.save(result("unknown", "three"))

    assert store.summary("test").win_rate == pytest.approx(50.0)
    assert store.summary("absent").win_rate == 0.0


def test_store_should_separate_players_when_match_id_is_shared(store: MatchStore) -> None:
    store.save(result("win", player_id="blue"))
    store.save(result("loss", player_id="orange"))

    assert store.summary("blue") == Summary(1, 0, 0)
    assert store.summary("orange") == Summary(0, 1, 0)


def test_store_should_retain_data_when_database_is_reopened(tmp_path: Path) -> None:
    path = tmp_path / "matches.sqlite3"
    first = MatchStore(path)
    first.save(result("win"))
    first.set_setting("player_id", "test")
    first.close()

    second = MatchStore(path)
    try:
        assert second.setting("player_id") == "test"
        assert second.summary("test") == Summary(1, 0, 0)
    finally:
        second.close()


def test_sessions_should_split_when_gap_reaches_one_hour(store: MatchStore) -> None:
    store.save(MatchResult("one", "test", "2026-10-02T18:00:00+00:00", 13, "win"))
    store.save(MatchResult("two", "test", "2026-10-02T18:59:00+00:00", 11, "loss"))
    store.save(MatchResult("three", "test", "2026-10-02T19:59:00+00:00", 11, "win"))

    starts = store.sessions("test")
    assert [row["started_at"] for row in starts] == [
        "2026-10-02T18:00:00+00:00",
        "2026-10-02T19:59:00+00:00",
    ]
    filtered = store.filtered_history("test", starts[0]["id"], 11, True)
    assert [row["outcome"] for row in filtered] == ["loss"]
    assert len(store.filtered_history("test", None, 11, True)) == 2
    assert len(store.filtered_history("test", starts[1]["id"], None)) == 1
