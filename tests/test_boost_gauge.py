"""Boost colors, exact thresholds and explicit transitions to and from empty."""

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern.boost_gauge import BoostGauge, boost_color


@pytest.mark.parametrize(
    ("value", "color"),
    [
        (100, "#23834a"),
        (51, "#23834a"),
        (50, "#c87518"),
        (26, "#c87518"),
        (25, "#b54242"),
        (1, "#b54242"),
        (0, "#b54242"),
        (None, "#617083"),
    ],
)
def test_gauge_should_apply_strict_color_thresholds(
    application: QApplication, value: int | None, color: str
) -> None:
    gauge = BoostGauge()
    gauge.set_boost("Équipier", value)

    assert boost_color(value) == color
    assert color in gauge.bar.styleSheet()
    assert gauge.name.text() == "Équipier"
    gauge.close()


def test_gauge_should_show_explicit_zero_with_busy_range_and_restore_received_values(
    application: QApplication,
) -> None:
    gauge = BoostGauge()
    gauge.set_boost("Équipier", 75)
    gauge.set_boost("Équipier", 0)

    assert gauge.bar.isEnabled()
    assert gauge.bar.minimum() == gauge.bar.maximum() == 0
    assert gauge.amount.text() == "0 % · vide"
    assert "0 % · boost vide" in gauge.bar.accessibleName()
    assert "#b54242" in gauge.bar.styleSheet()

    gauge.set_boost("Équipier", 0)
    assert gauge.bar.maximum() == 0
    gauge.set_boost("Équipier", 65)
    assert gauge.bar.maximum() == 100
    assert gauge.bar.value() == 65
    assert gauge.amount.text() == "65 %"
    assert "#23834a" in gauge.bar.styleSheet()
    gauge.close()


def test_gauge_should_stop_busy_mode_when_boost_becomes_unavailable(
    application: QApplication,
) -> None:
    gauge = BoostGauge()
    gauge.set_boost("Équipier", 0)

    gauge.set_boost("Équipier", None)

    assert not gauge.bar.isEnabled()
    assert gauge.bar.maximum() == 100
    assert gauge.amount.text() == "—"
    assert "champ non reçu" in gauge.bar.format()
    assert "champ non reçu" in gauge.bar.accessibleName()
    assert "#b54242" not in gauge.bar.styleSheet()
    gauge.close()
