"""Session totals preserve missing-data semantics and use the full filtered history."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from rl_winloose.match_data import MatchSnapshot, PlayerStats
from rl_winloose.match_panel import MatchPanel
from rl_winloose.statistics import STAT_LABELS, StatTotal, aggregate_statistics
from rl_winloose.storage import MatchStore
from rl_winloose.tracker import MatchResult


def counters(**values: int | None) -> dict[str, int | None]:
    """Supply explicitly missing counters alongside the specified observations."""
    row: dict[str, int | None] = dict.fromkeys(STAT_LABELS)
    row.update(values)
    return row


def test_statistics_should_include_zeroes_and_exclude_missing_values_from_each_average() -> None:
    rows = [counters(goals=2, saves=0), counters(goals=0), counters()]

    statistics = aggregate_statistics(rows)

    assert statistics["goals"] == StatTotal(total=2, matches=2)
    assert statistics["goals"].average == pytest.approx(1.0)
    assert statistics["saves"] == StatTotal(total=0, matches=1)
    assert statistics["saves"].average == 0.0
    assert statistics["shots"] == StatTotal(total=None, matches=0)
    assert statistics["shots"].average is None


def test_statistics_should_show_no_total_or_average_when_session_is_empty() -> None:
    statistics = aggregate_statistics([])

    assert set(statistics) == set(STAT_LABELS)
    assert all(statistic.total is None for statistic in statistics.values())
    assert all(statistic.average is None for statistic in statistics.values())


@pytest.fixture
def store() -> Iterator[MatchStore]:
    database = MatchStore(":memory:")
    yield database
    database.close()


def save_match(store: MatchStore, guid: str, timestamp: str, playlist: int | None) -> None:
    """Save contrasting player stats to catch accidental aggregation across players."""
    store.save(MatchResult(guid, "test", timestamp, playlist, "win"))
    store.save(MatchResult(guid, "other", timestamp, playlist, "loss"))
    store.save_details(
        MatchSnapshot(
            guid=guid,
            observed_at=timestamp,
            playlist=playlist,
            players={
                "test": PlayerStats("test", "Test", 0, goals=1, saves=0),
                "other": PlayerStats("other", "Other", 1, goals=9),
            },
        )
    )


def test_panel_should_aggregate_all_matches_when_history_exceeds_display_limit(
    application: QApplication,
    store: MatchStore,
) -> None:
    started_at = datetime(2026, 10, 4, 12, tzinfo=UTC)
    for index in range(101):
        timestamp = (started_at + timedelta(minutes=index)).isoformat()
        save_match(store, f"match-{index}", timestamp, 11)
    session_id = store.sessions("test")[0]["id"]
    panel = MatchPanel("test", "Test")
    panel.refresh(store, "test")
    panel.period.setCurrentIndex(panel.period.findData(session_id))

    assert panel.history.rowCount() == 100
    assert "101 victoires" in panel.counters.text()
    assert panel.statistics.values["goals"].text() == "101"
    assert panel.statistics.averages["goals"].text() == "1.0 / match · 101/101"
    assert "0 états de fin reçus" in panel.statistics.coverage.text()
    panel.close()


def test_panel_should_scope_statistics_to_session_playlist_and_selected_player(
    application: QApplication,
    store: MatchStore,
) -> None:
    save_match(store, "old", "2026-10-03T12:00:00+00:00", 11)
    save_match(store, "duos", "2026-10-04T12:00:00+00:00", 11)
    save_match(store, "trios", "2026-10-04T12:10:00+00:00", 13)
    save_match(store, "unclassified", "2026-10-04T12:20:00+00:00", None)
    session_id = store.sessions("test")[-1]["id"]
    panel = MatchPanel("test", "Test")
    panel.refresh(store, "test")
    panel.period.setCurrentIndex(panel.period.findData(session_id))
    panel.playlist_filter.setCurrentIndex(panel.playlist_filter.findData("all"))
    assert panel.statistics.values["goals"].text() == "3"

    panel.playlist_filter.setCurrentIndex(panel.playlist_filter.findData(11))
    assert panel.statistics.values["goals"].text() == "1"
    panel.playlist_filter.setCurrentIndex(panel.playlist_filter.findData(None))
    assert panel.statistics.values["goals"].text() == "1", "Unknown playlist is a real filter"
    panel.period.setCurrentIndex(panel.period.findData("all"))
    panel.playlist_filter.setCurrentIndex(panel.playlist_filter.findData("all"))
    assert panel.statistics.values["goals"].text() == "4"
    panel.refresh(store, "other")
    assert panel.statistics.values["goals"].text() == "36"
    panel.close()
