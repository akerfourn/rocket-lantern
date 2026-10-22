"""Team sums, missing counters, grouping and in-place translation of the live table."""

from dataclasses import astuple, replace

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from rocket_lantern.branding import ASSET_DIRECTORY
from rocket_lantern.i18n import language_manager
from rocket_lantern.live_match_panel import LiveMatchPanel
from rocket_lantern.live_team_table import (
    ENCOUNTER_ROLE,
    LIVE_STAT_LABELS,
    TEAM_COLORS,
    TEAM_ROLE,
    LiveTeamTable,
    team_totals,
)
from rocket_lantern.match_data import PlayerStats
from rocket_lantern.player_encounter_icons import ENCOUNTER_COLORS, player_encounter_icon
from rocket_lantern.player_encounters import EncounterScope
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


def test_live_table_should_show_totals_in_colored_team_headings_with_compact_stat_headers(
    application: QApplication,
) -> None:
    players = (*teammates(), PlayerStats("c", "Comet", 1, score=50))
    table = LiveTeamTable()
    table.update_players(players, "b")

    assert table.columnCount() == 1 + len(LIVE_STAT_LABELS)
    assert [table.horizontalHeaderItem(column).text() for column in range(table.columnCount())] == [
        "Joueur",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]
    for column, label in enumerate(LIVE_STAT_LABELS.values(), start=1):
        item = table.horizontalHeaderItem(column)
        if column == 4:
            assert "arrêts miraculeux observés" in item.toolTip()
        elif column == 5:
            assert "Poteaux et transversale adverses" in item.toolTip()
        else:
            assert item.toolTip() == label
        assert item.data(Qt.ItemDataRole.AccessibleTextRole) == label
        assert not item.icon().isNull()
    assert table.rowCount() == 6
    assert table.item(0, 0).text() == "Équipe bleue"
    assert table.item(4, 0).text() == "Équipe orange"
    assert [table.item(0, column).text() for column in range(1, table.columnCount())] == [
        "320",
        "2",
        "1",
        "4",
        "0",
        "6",
        "20",
        "1",
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


def test_live_table_should_keep_headers_and_counters_together_in_the_requested_order(
    application: QApplication,
) -> None:
    table = LiveTeamTable()
    table.update_players(teammates(), "b", {"a": 2}, opponent_post_hits={"a": 1, "b": 3})

    assert [
        table.horizontalHeaderItem(column).data(Qt.ItemDataRole.AccessibleTextRole)
        for column in range(1, table.columnCount())
    ] == [
        "Points",
        "Buts",
        "Passes décisives",
        "Arrêts",
        "Poteaux adverses",
        "Tirs",
        "Touches de balle",
        "Démolitions",
        "Contacts voitures",
    ]
    assert [
        [table.item(row, column).text() for column in range(1, table.columnCount())]
        for row in range(table.rowCount())
    ] == [
        ["320", "2", "1", "4 (2)", "4", "6", "20", "1", "11"],
        ["200", "2", "0", "1", "3", "2", "8", "1", "6"],
        ["120", "0", "1", "3 (2)", "1", "4", "12", "0", "5"],
    ]
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


def test_live_table_should_resize_saves_for_epic_counts_and_refresh_without_new_player_stats(
    application: QApplication,
) -> None:
    table = LiveTeamTable()
    table.update_players(teammates(), "a")
    table.show()
    application.processEvents()
    initial_width = table.columnWidth(4)
    epic_saves = {"a": 1, "absent": 99}

    table.update_players(teammates(), "a", epic_saves)
    application.processEvents()

    assert table.item(0, 4).text() == "4 (1)", "Only present players contribute to the total"
    assert table.item(1, 4).text() == "1", "Zero epic saves must not append (0)"
    assert table.item(2, 4).text() == "3 (1)"

    epic_saves["a"] = 2
    table.update_players(teammates(), "a", epic_saves)
    application.processEvents()
    assert table.item(0, 4).text() == "4 (2)"
    assert table.item(2, 4).text() == "3 (2)", "An event alone must invalidate the table cache"

    first, second = teammates()
    epic_saves["a"] = 12
    table.update_players((replace(first, saves=30), second), "a", epic_saves)
    application.processEvents()
    assert table.item(0, 4).text() == "31 (12)"
    assert table.columnWidth(4) > initial_width
    for row in (0, 2):
        item = table.item(row, 4)
        assert table.columnWidth(4) >= QFontMetrics(item.font()).horizontalAdvance(item.text())
    assert first.saves == 3, "Formatting must not modify the source counters"
    table.close()


def test_live_table_should_keep_missing_and_partial_saves_unknown_with_observed_epic_counts(
    application: QApplication,
) -> None:
    first, second = teammates()
    players = (replace(first, saves=None), second)
    table = LiveTeamTable()
    table.update_players(players, "a", {"a": 1})

    assert table.item(0, 4).text() == "≥ 1 (1)"
    assert "1/2" in table.item(0, 4).toolTip()
    assert table.item(2, 4).text() == "— (1)"
    assert players[0].saves is None

    table.update_players((players[0],), "a", {"a": 1})
    assert table.item(0, 4).text() == "— (1)"
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
        assert table.item(0, 8).text() == "—"
        assert table.item(0, 8).toolTip() == "No value received."
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


def test_live_table_should_translate_icon_descriptions_in_place_without_changing_icons(
    application: QApplication,
) -> None:
    manager = language_manager()
    previous = manager.language
    manager.set_language("fr")
    table = LiveTeamTable()
    table.show()
    headers = [table.horizontalHeaderItem(column) for column in range(table.columnCount())]
    icons = [item.icon().cacheKey() for item in headers]
    try:
        assert headers[3].toolTip() == "Passes décisives"
        manager.set_language("en")
        application.processEvents()

        assert [item.toolTip() for item in headers[1:]] == [
            "Points",
            "Goals",
            "Assists",
            "Saves · in parentheses: observed epic saves.",
            "Opponent posts and crossbar hit · observed events.",
            "Shots",
            "Ball touches",
            "Demolitions",
            "Car contacts",
        ]
        for column, item in enumerate(headers):
            assert table.horizontalHeaderItem(column) is item
            assert item.icon().cacheKey() == icons[column]
            if column == 4:
                assert item.data(Qt.ItemDataRole.AccessibleTextRole) == "Saves"
            elif column == 5:
                assert item.data(Qt.ItemDataRole.AccessibleTextRole) == "Opponent goal frame hits"
            elif column > 0:
                assert item.data(Qt.ItemDataRole.AccessibleTextRole) == item.toolTip()
        assert headers[0].text() == "Player"
        assert all(item.text() == "" for item in headers[1:])
    finally:
        table.close()
        manager.set_language(previous)
        application.processEvents()


def test_live_table_should_mark_known_players_without_new_columns_or_replacing_rows(
    application: QApplication,
) -> None:
    table = LiveTeamTable()
    players = (*teammates(), PlayerStats("c", "Comet", 1, score=50))
    table.update_players(players, "b")
    nova = table.item(2, 0)
    comet = table.item(5, 0)

    table.set_encounters(
        {"a": EncounterScope.SESSION, "b": EncounterScope.SESSION, "c": EncounterScope.HISTORY}
    )

    assert table.columnCount() == 1 + len(LIVE_STAT_LABELS)
    assert table.item(2, 0) is nova
    assert table.item(5, 0) is comet
    assert nova.text() == "Nova"
    assert nova.data(ENCOUNTER_ROLE) == EncounterScope.SESSION
    assert nova.toolTip() == "Nova\nDéjà croisé dans la session actuelle."
    assert comet.data(ENCOUNTER_ROLE) == EncounterScope.HISTORY
    assert comet.toolTip() == "Comet\nDéjà croisé dans l’historique."
    assert table.item(1, 0).data(ENCOUNTER_ROLE) is None, "Never mark the tracked player"
    assert table.item(0, 0).data(ENCOUNTER_ROLE) is None, "Team totals are not participants"
    assert table.item(0, 1).text() == "320"

    table.set_encounters({})
    assert table.item(2, 0) is nova
    assert nova.data(ENCOUNTER_ROLE) is None
    assert nova.toolTip() == "Nova"
    table.close()


def test_live_table_should_translate_encounter_tooltips_and_clear_stale_accessibility_text(
    application: QApplication,
) -> None:
    manager = language_manager()
    previous = manager.language
    manager.set_language("fr")
    table = LiveTeamTable()
    table.update_players(teammates(), "b")
    table.set_encounters({"a": EncounterScope.SESSION})
    table.show()
    name = table.item(2, 0)
    icon = name.icon().cacheKey()
    try:
        manager.set_language("en")
        application.processEvents()

        assert table.item(2, 0) is name
        assert name.text() == "Nova"
        assert name.icon().cacheKey() == icon
        assert name.toolTip() == "Nova\nPreviously met in the current session."
        assert name.data(Qt.ItemDataRole.AccessibleTextRole) == name.toolTip()

        table.set_encounters({"a": EncounterScope.HISTORY})
        assert name.toolTip() == "Nova\nPreviously met in saved history."
        table.set_encounters({})
        manager.set_language("fr")
        application.processEvents()
        assert name.toolTip() == "Nova"
        assert name.data(Qt.ItemDataRole.AccessibleTextRole) == "Nova"
    finally:
        table.close()
        manager.set_language(previous)
        application.processEvents()


def test_encounter_icons_should_retain_team_stripes_and_use_distinct_scope_colors(
    application: QApplication,
) -> None:
    assert QSvgRenderer(str(ASSET_DIRECTORY / "player-seen.svg")).isValid()
    for scope in (None, *EncounterScope):
        icon = player_encounter_icon(TEAM_COLORS[0], scope)
        image = icon.pixmap(QSize(26, 16), 2).toImage()
        colors = {
            image.pixelColor(x, y).name()
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() == 255
        }
        assert QColor(TEAM_COLORS[0]).name() in colors
        if scope is None:
            assert colors == {TEAM_COLORS[0]}
        else:
            assert ENCOUNTER_COLORS[scope] in colors
