"""A persistent-result banner does not count unknown outcomes in the win rate."""

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from rocket_lantern.result_summary import ResultSummary, balance_icon, outcome_icon
from rocket_lantern.storage import Summary


def test_summary_should_show_balance_win_rate_and_unknown_results(
    application: QApplication,
) -> None:
    panel = ResultSummary()
    panel.set_summary(Summary(3, 1, 2))

    assert panel.wins.text() == "3 victoires"
    assert panel.losses.text() == "1 défaites"
    assert panel.balance.text() == "+2"
    assert panel.rate.text() == "75,0 % de victoires"
    assert panel.unknown.text() == "2 inconnus"
    assert panel.accessibleName() == panel.text()
    assert not outcome_icon("win").isNull()
    assert not outcome_icon("loss").isNull()
    panel.set_summary(Summary(0, 2, 1))
    assert panel.balance.text() == "-2"
    assert panel.rate.text() == "0,0 % de victoires"
    panel.close()


def test_summary_should_place_icon_only_assessment_immediately_after_delta(
    application: QApplication,
) -> None:
    panel = ResultSummary()
    panel.resize(1000, 110)
    panel.show()
    application.processEvents()

    counts = panel.layout().itemAt(1).layout()
    assert counts.itemAt(counts.indexOf(panel.balance) + 1).widget() is panel.evaluations
    assert panel.evaluation.parent() is panel.evaluations
    assert panel.evaluation.text() == ""
    assert panel.evaluation.width() == 40
    badge_rect = panel.evaluation.geometry().translated(panel.evaluations.pos())
    assert badge_rect.left() > panel.balance.geometry().right()
    assert abs(badge_rect.center().y() - panel.balance.geometry().center().y()) <= 1
    panel.close()


def test_summary_should_offer_overlay_settings_even_without_recorded_matches(
    application: QApplication,
) -> None:
    panel = ResultSummary()
    panel.resize(1000, 120)
    panel.show()
    application.processEvents()
    requests = []
    panel.overlay_requested.connect(lambda: requests.append(True))

    panel.overlay_button.click()

    assert requests == [True]
    assert panel.overlay_button.isVisible()
    assert panel.overlay_button.isEnabled()
    assert panel.overlay_button.text() == ""
    assert panel.overlay_button.iconSize().width() == 14
    assert panel.overlay_button.width() == panel.overlay_button.height() == 22
    assert not panel.overlay_button.icon().isNull()
    assert panel.overlay_button.toolTip() == "Configurer l’overlay du bilan W/L"
    assert panel.overlay_button.accessibleName() == panel.overlay_button.toolTip()
    assert panel.overlay_button.geometry().left() > panel.context.geometry().right()
    panel.close()


@pytest.mark.parametrize(
    ("wins", "losses", "text", "description"),
    [
        (3, 1, "+2", "Bilan positif"),
        (1, 3, "-2", "Bilan négatif"),
        (2, 2, "+0", "Bilan équilibré"),
    ],
)
def test_summary_should_emphasize_delta_and_update_its_symbol_when_balance_changes(
    application: QApplication, wins: int, losses: int, text: str, description: str
) -> None:
    panel = ResultSummary()
    panel.set_summary(Summary(5, 0, 0))

    panel.set_summary(Summary(wins, losses, 1))
    panel.show()
    application.processEvents()

    assert panel.balance.text() == text
    assert panel.balance.font().pixelSize() == panel.wins.font().pixelSize() == 23
    assert panel.balance_symbol.accessibleName() == description
    assert not panel.balance_symbol.pixmap().isNull()
    assert panel.balance_symbol.size().width() == 28
    assert not balance_icon(wins - losses).isNull()
    panel.close()


@pytest.mark.parametrize("summary", [Summary(0, 0, 0), Summary(12, 3, 0), Summary(3, 12, 0)])
def test_summary_should_align_count_line_boxes_and_symbols_when_delta_has_different_glyphs(
    application: QApplication, summary: Summary
) -> None:
    panel = ResultSummary()
    panel.resize(1000, 160)
    panel.set_summary(summary)
    panel.show()
    application.processEvents()

    counts = (panel.wins, panel.losses, panel.balance)
    assert len({count.geometry().top() for count in counts}) == 1
    assert len({count.height() for count in counts}) == 1
    assert len({count.fontMetrics().ascent() for count in counts}) == 1
    symbols = [label for label in panel.findChildren(QLabel) if not label.pixmap().isNull()]
    assert len(symbols) == 3
    for symbol in symbols:
        assert abs(symbol.geometry().center().y() - panel.balance.geometry().center().y()) <= 1
    assert "(" not in panel.balance.text()
    assert ")" not in panel.balance.text()
    panel.close()
