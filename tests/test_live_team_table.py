"""Team sums, missing counters, grouping and in-place translation of the live table."""

from dataclasses import astuple, replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rocket_lantern.i18n import language_manager
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.live_team_table import TEAM_ROLE, LiveTeamTable, team_totals
from rocket_lantern.match_data import PlayerStats
from rocket_lantern.statistics import STAT_LABELS


def teammates() -> tuple[PlayerStats, PlayerStats]:
    return (
        PlayerStats(
            "a",
            "Nova",
            0,
            score=120,
            goals=0,
            assists=1,
            saves=3,
            shots=4,
            demos=0,
            touches=12,
            car_touches=5,
        ),
        PlayerStats(
            "b",
            "Orbit",
            0,
            score=200,
            goals=2,
            assists=0,
            saves=1,
            shots=2,
            demos=1,
            touches=8,
            car_touches=6,
        ),
    )


def test_team_totals_should_sum_each_column_without_changing_the_players() -> None:
    players = teammates()
    before = tuple(astuple(player) for player in players)

    totals = team_totals(players)

    assert {field: total.value for field, total in totals.items()} == {
        "score": 320,
        "goals": 2,
        "assists": 1,
        "saves": 4,
        "shots": 6,
        "demos": 1,
        "touches": 20,
        "car_touches": 11,
    }
    assert all(total.known_players == total.player_count == 2 for total in totals.values())
    assert tuple(astuple(player) for player in players) == before


def test_team_totals_should_distinguish_partial_zero_from_complete_zero_and_missing() -> None:
    players = (
        PlayerStats("a", "Nova", 0, score=0, goals=0),
        PlayerStats("b", "Orbit", 0, goals=0),
    )

    totals = team_totals(players)

    assert totals["score"].value == 0
    assert totals["score"].known_players == 1
    assert totals["score"].display() == "≥ 0"
    assert totals["goals"].display() == "0"
    assert totals["assists"].value is None
    assert totals["assists"].known_players == 0
    assert totals["assists"].display() == "—"


def test_team_totals_should_keep_empty_teams_unknown_instead_of_inventing_zeroes() -> None:
    totals = team_totals(())

    assert set(totals) == set(STAT_LABELS)
    assert all(total.value is None and total.player_count == 0 for total in totals.values())


def test_live_table_should_show_totals_in_colored_team_headings_and_keep_stat_labels(
    application: QApplication,
) -> None:
    players = (*teammates(), PlayerStats("c", "Comet", 1, score=50))
    table = LiveTeamTable()
    table.update_players(players, "b")

    assert table.columnCount() == 1 + len(STAT_LABELS)
    assert [table.horizontalHeaderItem(column).text() for column in range(table.columnCount())] == [
        "Joueur",
        *STAT_LABELS.values(),
    ]
    assert table.rowCount() == 6
    assert table.item(0, 0).text() == "Équipe bleue"
    assert table.item(4, 0).text() == "Équipe orange"
    assert [table.item(0, column).text() for column in range(1, table.columnCount())] == [
        "320",
        "2",
        "1",
        "4",
        "6",
        "1",
        "20",
        "11",
    ]
    assert table.item(4, 1).text() == "50", "The opposing team must not enter the blue totals"
    assert table.item(0, 0).data(Qt.ItemDataRole.UserRole) is None
    assert not table.item(0, 0).flags() & Qt.ItemFlag.ItemIsSelectable
    assert table.item(1, 0).data(Qt.ItemDataRole.UserRole) == "b"
    assert table.item(1, 0).font().bold()
    assert not table.item(2, 0).font().bold()
    assert table.item(0, 1).data(TEAM_ROLE) == table.item(1, 1).data(TEAM_ROLE) == 0
    assert table.item(4, 1).data(TEAM_ROLE) == 1
    assert table.item(0, 1).background().color() != table.item(4, 1).background().color()
    assert (
        table.item(0, 1).background().color().alpha()
        > table.item(1, 1).background().color().alpha()
    )
    table.close()


def test_live_table_should_refresh_totals_on_departure_and_clear_stale_group_spans(
    application: QApplication,
) -> None:
    blue = teammates()
    players = (*blue, PlayerStats("c", "Comet", 1, score=50))
    table = LiveTeamTable()
    table.update_players(players, "b")
    assert table.columnSpan(3, 0) == table.columnCount()

    table.update_players((blue[0],), "b")

    assert table.rowCount() == 2
    assert table.item(0, 1).text() == "120"
    assert table.item(1, 0).text() == "Nova"
    assert table.columnSpan(1, 0) == 1
    table.clear_players()
    assert table.rowCount() == 0
    table.update_players(players, "b")
    assert table.item(0, 1).text() == "320", "Reconnect must rebuild even an identical snapshot"
    table.close()


def test_live_table_should_translate_partial_total_tooltips_without_rebuilding_rows(
    application: QApplication,
) -> None:
    manager = language_manager()
    previous = manager.language
    manager.set_language("fr")
    first, second = teammates()
    table = LiveTeamTable()
    table.update_players((replace(first, score=None, demos=None), replace(second, demos=None)), "b")
    table.show()
    total = table.item(0, 1)
    try:
        assert total.text() == "≥ 200"
        assert "1/2" in total.toolTip()
        manager.set_language("en")
        application.processEvents()

        assert table.item(0, 0).text() == "Blue team"
        assert table.item(0, 0).toolTip() == "Total for present players"
        assert table.item(0, 1) is total
        assert "Partial total" in total.toolTip()
        assert "1/2" in total.toolTip()
        assert total.text() == "≥ 200"
        assert table.item(0, 6).text() == "—"
        assert table.item(0, 6).toolTip() == "No value received."
    finally:
        table.close()
        manager.set_language(previous)
        application.processEvents()


def test_live_table_should_not_rebuild_for_boost_only_updates(
    application: QApplication,
) -> None:
    panel = LiveMatchPanel("local")
    message = {
        "Event": "UpdateState",
        "Data": {
            "MatchGuid": "boost-only",
            "Game": {},
            "Players": [
                {"PrimaryId": "local", "Name": "Nova", "TeamNum": 0, "Boost": 50, "Score": 100}
            ],
        },
    }
    panel.observe(message, "2026-10-22T20:00:00+00:00", False)
    heading = panel.players.item(0, 0)
    player = panel.players.item(1, 0)
    message["Data"]["Players"][0]["Boost"] = 25

    panel.observe(message, "2026-10-22T20:00:01+00:00", False)

    assert panel.players.item(0, 0) is heading
    assert panel.players.item(1, 0) is player
    assert panel.boost.value() == 25
    assert panel.players.item(0, 1).text() == "100"
    panel.close()
