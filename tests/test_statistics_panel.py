"""Average-first statistic cards reuse the live icons without visible sample counts."""

import pytest
from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QLabel

from rocket_lantern.branding import ASSET_DIRECTORY
from rocket_lantern.i18n import language_manager
from rocket_lantern.statistics import STAT_LABELS
from rocket_lantern.statistics_panel import SUMMARY_FIELDS, StatisticsPanel


def counters(**values: int | None) -> dict[str, int | None]:
    row: dict[str, int | None] = dict.fromkeys(STAT_LABELS)
    row.update(values)
    return row


def test_cards_should_show_large_means_with_small_units_without_totals_or_visible_sample_counts(
    application: QApplication,
) -> None:
    panel = StatisticsPanel()
    panel.update_rows(
        [counters(score=100, goals=2, saves=0), counters(score=200, goals=0), counters()]
    )
    panel.show()
    application.processEvents()

    assert panel.values["score"].text() == "150,0", "Show the mean, not the cumulative 300"
    assert panel.values["goals"].text() == "1,0", "A received zero must enter the denominator"
    assert panel.values["saves"].text() == "0,0"
    assert panel.values["shots"].text() == "—", "Missing observations are not zeroes"
    assert all(unit.text() == "/ match" for unit in panel.units.values())
    assert panel.values["score"].font().pixelSize() > panel.units["score"].font().pixelSize()
    value = panel.values["score"]
    unit = panel.units["score"]
    value_baseline = value.mapTo(panel, QPoint()).y() + value.fontMetrics().ascent()
    unit_baseline = unit.mapTo(panel, QPoint()).y() + unit.fontMetrics().ascent()
    assert abs(value_baseline - unit_baseline) <= 1
    assert "2 matchs renseignés sur 3" in panel.values["score"].toolTip()
    assert panel.cards["score"].toolTip() == panel.values["score"].toolTip()
    texts = [label.text() for label in panel.findChildren(QLabel) if label.isVisible()]
    assert "300" not in texts
    assert not any("/3" in text or "renseignés" in text or "Totaux" in text for text in texts)
    panel.close()


def test_cards_should_clear_previous_means_when_the_selected_period_has_no_data(
    application: QApplication,
) -> None:
    panel = StatisticsPanel()
    panel.update_rows([counters(goals=4)])

    panel.update_rows(())

    assert all(value.text() == "—" for value in panel.values.values())
    assert "0 matchs renseignés sur 0" in panel.values["goals"].toolTip()
    assert panel.values["goals"].accessibleName() == "Buts : — par match"
    panel.close()


def test_cards_should_translate_existing_means_titles_and_coverage_without_rebuilding_widgets(
    application: QApplication,
) -> None:
    manager = language_manager()
    previous = manager.language
    manager.set_language("fr")
    panel = StatisticsPanel()
    panel.update_rows([counters(goals=1), counters(goals=2)])
    panel.show()
    application.processEvents()
    value = panel.values["goals"]
    icon = panel.icons["goals"].pixmap().toImage()
    try:
        manager.set_language("en")
        application.processEvents()

        assert panel.values["goals"] is value
        assert value.text() == "1.5"
        assert value.accessibleName() == "Goals: 1.5 per match"
        assert "2 matches" in value.toolTip()
        assert "Buts" not in [label.text() for label in panel.findChildren(QLabel)]
        assert panel.icons["goals"].accessibleName() == "Goals"
        assert panel.icons["goals"].pixmap().toImage() == icon
    finally:
        panel.close()
        manager.set_language(previous)
        application.processEvents()


@pytest.mark.parametrize("foreground", ["#17202b", "#edf1f7"])
def test_cards_should_render_the_shared_svgs_in_display_order_and_follow_palette_changes(
    application: QApplication, foreground: str
) -> None:
    panel = StatisticsPanel()
    assert tuple(panel.cards) == (
        "score",
        "goals",
        "assists",
        "saves",
        "shots",
        "touches",
        "demos",
        "car_touches",
    )
    for index, field in enumerate(SUMMARY_FIELDS):
        assert panel.layout().itemAtPosition(index // 4, index % 4).widget() is panel.cards[field]
        label = panel.icons[field]
        palette = label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor(foreground))
        label.setPalette(palette)
        image = label.pixmap().toImage()
        expected = QIcon(str(ASSET_DIRECTORY / f"stat-{field}.svg"))
        source = expected.pixmap(QSize(20, 20), label.devicePixelRatioF()).toImage()
        assert not image.isNull()
        assert image.size() == source.size()
        assert image.pixelColor(0, 0).alpha() == 0
        assert any(
            image.pixelColor(x, y) == QColor(foreground)
            for x in range(image.width())
            for y in range(image.height())
        )
        assert all(
            image.pixelColor(x, y).alpha() == source.pixelColor(x, y).alpha()
            for x in range(image.width())
            for y in range(image.height())
        ), f"The {field} card must reuse its live-table SVG"
    panel.close()
