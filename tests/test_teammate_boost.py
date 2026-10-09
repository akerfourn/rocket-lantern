"""Named teammate gauges follow current IDs, teams and received boost only."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern.live_match_panel import LiveMatchPanel

OBSERVED_AT = "2026-10-08T19:00:00+00:00"


def state_message(players: list[dict[str, object]]) -> dict[str, object]:
    return {
        "Event": "UpdateState",
        "Data": {"MatchGuid": "live-team", "Game": {}, "Players": players},
    }


@pytest.fixture
def panel(application: QApplication) -> Iterator[LiveMatchPanel]:
    widget = LiveMatchPanel("selected")
    widget.show()
    yield widget
    widget.close()


def test_panel_should_show_only_other_players_of_selected_team_even_with_duplicate_names(
    panel: LiveMatchPanel,
) -> None:
    panel.observe(
        state_message(
            [
                {"PrimaryId": "selected", "Name": "Same", "TeamNum": 0, "Boost": 90},
                {"PrimaryId": "mate-1", "Name": "Same", "TeamNum": 0, "Boost": 65},
                {"PrimaryId": "mate-2", "Name": "Second", "TeamNum": 0, "Boost": 25},
                {"PrimaryId": "opponent", "Name": "Other", "TeamNum": 1, "Boost": 100},
            ]
        ),
        OBSERVED_AT,
        False,
    )

    assert set(panel.teammate_gauges) == {"mate-1", "mate-2"}
    assert panel.teammate_gauges["mate-1"].name.text() == "Same"
    assert panel.teammate_gauges["mate-1"].bar.value() == 65
    assert "#23834a" in panel.teammate_gauges["mate-1"].bar.styleSheet()
    assert panel.teammate_gauges["mate-2"].bar.value() == 25
    assert "#b54242" in panel.teammate_gauges["mate-2"].bar.styleSheet()
    assert panel.boost.value() == 90
    assert panel.teammates_hint.isHidden()


def test_panel_should_reuse_gauges_and_clear_missing_values_on_each_received_state(
    panel: LiveMatchPanel,
) -> None:
    selected = {"PrimaryId": "selected", "Name": "Me", "TeamNum": 0, "Boost": 75}
    panel.observe(
        state_message(
            [
                selected,
                {"PrimaryId": "mate", "Name": "Before", "TeamNum": 0, "Boost": 45},
            ]
        ),
        OBSERVED_AT,
        False,
    )
    gauge = panel.teammate_gauges["mate"]

    panel.observe(
        state_message(
            [
                selected,
                {"PrimaryId": "mate", "Name": "After", "TeamNum": 0, "Boost": 0},
            ]
        ),
        OBSERVED_AT,
        False,
    )
    assert panel.teammate_gauges["mate"] is gauge
    assert gauge.name.text() == "After"
    assert gauge.bar.maximum() == 0
    assert gauge.amount.text() == "0 % · vide"
    panel.observe(
        state_message(
            [
                selected,
                {"PrimaryId": "mate", "Name": "After", "TeamNum": 0},
            ]
        ),
        OBSERVED_AT,
        False,
    )
    assert panel.teammate_gauges["mate"] is gauge
    assert gauge.bar.maximum() == 0
    assert gauge.bar.isEnabled()
    assert gauge.amount.text() == "≈ 0 %", "Omitted boost must be marked as an assumption"
    assert panel.state.boost["mate"] is None, "The received state must not invent a zero"


def test_panel_should_switch_teams_and_remove_departed_gauges_when_selection_changes(
    panel: LiveMatchPanel,
) -> None:
    panel.observe(
        state_message(
            [
                {"PrimaryId": "selected", "Name": "Blue", "TeamNum": 0, "Boost": 75},
                {"PrimaryId": "blue-mate", "Name": "Mate", "TeamNum": 0, "Boost": 40},
                {"PrimaryId": "orange-1", "Name": "Orange", "TeamNum": 1, "Boost": 30},
                {"PrimaryId": "orange-2", "Name": "Other", "TeamNum": 1},
            ]
        ),
        OBSERVED_AT,
        False,
    )
    previous_gauge = panel.teammate_gauges["blue-mate"]

    panel.set_player("orange-1")
    assert set(panel.teammate_gauges) == {"orange-2"}
    assert previous_gauge.isHidden()
    assert panel.teammate_gauges["orange-2"].bar.maximum() == 0
    assert panel.teammate_gauges["orange-2"].amount.text() == "≈ 0 %"
    assert panel.boost.value() == 30
    panel.observe(
        state_message(
            [
                {"PrimaryId": "orange-1", "Name": "Orange", "TeamNum": 1, "Boost": 30},
            ]
        ),
        OBSERVED_AT,
        False,
    )
    assert panel.teammate_gauges == {}
    assert "Aucun coéquipier" in panel.teammates_hint.text()
    assert not panel.teammates_hint.isHidden()


def test_panel_should_not_guess_a_team_without_a_present_selected_player(
    panel: LiveMatchPanel,
) -> None:
    panel.observe(
        state_message(
            [
                {"PrimaryId": "other", "Name": "Other", "TeamNum": 0, "Boost": 80},
            ]
        ),
        OBSERVED_AT,
        False,
    )

    assert panel.teammate_gauges == {}
    assert "Sélectionne un joueur présent" in panel.teammates_hint.text()
    assert not panel.boost.isEnabled()


def test_panel_should_clear_teammates_on_disconnect_and_exclude_historical_replays(
    panel: LiveMatchPanel,
) -> None:
    message = state_message(
        [
            {"PrimaryId": "selected", "Name": "Me", "TeamNum": 0, "Boost": 80},
            {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, "Boost": 0},
        ]
    )
    panel.observe(message, OBSERVED_AT, False)
    assert "mate" in panel.teammate_gauges

    panel.clear("Déconnecté")
    assert panel.teammate_gauges == {}
    assert "En attente" in panel.teammates_hint.text()
    assert not panel.boost.isEnabled()
    assert panel.boost.maximum() == 100
    panel.observe(message, OBSERVED_AT, True)
    assert panel.teammate_gauges == {}
    assert panel.state.snapshot is None


@pytest.mark.parametrize("fields", [{"Boost": 101}, {"Boost": None}, {"bHasCar": False}])
def test_panel_should_not_assume_zero_for_invalid_values_or_an_absent_car(
    panel: LiveMatchPanel, fields: dict[str, object]
) -> None:
    panel.observe(
        state_message(
            [
                {"PrimaryId": "selected", "Name": "Me", "TeamNum": 0, "Boost": 75},
                {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, **fields},
            ]
        ),
        OBSERVED_AT,
        False,
    )

    gauge = panel.teammate_gauges["mate"]
    assert not gauge.bar.isEnabled()
    assert gauge.amount.text() == "—"
    assert "mate" not in panel.state.omitted_boost


def test_panel_should_restore_real_teammate_boost_after_an_omitted_value(
    panel: LiveMatchPanel,
) -> None:
    selected = {"PrimaryId": "selected", "Name": "Me", "TeamNum": 0}
    panel.observe(
        state_message(
            [
                selected,
                {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0},
            ]
        ),
        OBSERVED_AT,
        False,
    )
    assert not panel.boost.isEnabled(), "The selected player's omitted boost is not inferred"
    gauge = panel.teammate_gauges["mate"]
    assert gauge.amount.text() == "≈ 0 %"
    panel.observe(
        state_message(
            [
                selected,
                {"PrimaryId": "mate", "Name": "Mate", "TeamNum": 0, "Boost": 80},
            ]
        ),
        OBSERVED_AT,
        False,
    )

    assert panel.teammate_gauges["mate"] is gauge
    assert gauge.bar.maximum() == 100
    assert gauge.bar.value() == 80
    assert gauge.amount.text() == "80 %"
    assert "#23834a" in gauge.bar.styleSheet()
    assert "mate" not in panel.state.omitted_boost
    assert panel.state.boost["mate"] == 80
