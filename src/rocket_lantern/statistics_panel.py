"""Per-match average cards, with data coverage available on hover."""

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from rocket_lantern.i18n import DisplayText
from rocket_lantern.i18n import text as T
from rocket_lantern.stat_icon import StatIcon
from rocket_lantern.statistics import STAT_LABELS, StatRow, aggregate_statistics
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import tooltip

SUMMARY_FIELDS = ("score", "goals", "assists", "saves", "shots", "touches", "demos", "car_touches")


class StatisticsPanel(QWidget):
    """Emphasize averages for one player without displaying cumulative counters."""

    def __init__(self) -> None:
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        self.cards: dict[str, QFrame] = {}
        self.icons: dict[str, StatIcon] = {}
        self.values: dict[str, QLabel] = {}
        self.units: dict[str, QLabel] = {}
        self.setStyleSheet(
            "QFrame#statCard { background: palette(base); border-radius: 6px; }"
            "QLabel#statValue { font-size: 26px; font-weight: 600; }"
            "QLabel#statUnit { font-size: 12px; }"
        )
        for index, field in enumerate(SUMMARY_FIELDS):
            grid.addWidget(self._create_card(field), index // 4, index % 4)
            grid.setColumnStretch(index % 4, 1)
        self._align_units()
        tooltip(
            self,
            T(
                "Les compteurs peuvent être partiels, même avec un état de fin si "
                "un joueur est parti avant. — : donnée absente ; 0 : zéro reçu. "
                "Les résultats inconnus sont inclus dans ces statistiques."
            ),
        )
        self.update_rows(())

    def _create_card(self, field: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        heading.setSpacing(6)
        self.icons[field] = StatIcon(field)
        heading.addWidget(self.icons[field])
        heading.addWidget(QLabel(T(STAT_LABELS[field])))
        heading.addStretch()
        layout.addLayout(heading)
        value_line = QHBoxLayout()
        value_line.setSpacing(6)
        self.values[field] = QLabel("—")
        self.values[field].setObjectName("statValue")
        self.units[field] = QLabel(T("/ match"))
        self.units[field].setObjectName("statUnit")
        value_line.addWidget(self.values[field], 0, Qt.AlignmentFlag.AlignBottom)
        value_line.addWidget(self.units[field], 0, Qt.AlignmentFlag.AlignBottom)
        value_line.addStretch()
        layout.addLayout(value_line)
        self.cards[field] = card
        return card

    def _align_units(self) -> None:
        """Align the small suffix with the number's text baseline, not its line-box bottom."""
        for field in SUMMARY_FIELDS:
            value = self.values[field]
            unit = self.units[field]
            value.ensurePolished()
            unit.ensurePolished()
            offset = max(0, value.fontMetrics().descent() - unit.fontMetrics().descent())
            unit.setContentsMargins(0, 0, 0, offset)

    def update_rows(self, rows: Sequence[StatRow]) -> None:
        """Use all filtered matches, not only the visible history rows."""
        for field, statistic in aggregate_statistics(rows).items():
            average: DisplayText = "—"
            if statistic.average is not None:
                average = T("{value:.1f}", value=statistic.average)
            self.values[field].setText(average)
            self.values[field].setAccessibleName(
                T(
                    "{statistic} : {average} par match",
                    statistic=T(STAT_LABELS[field]),
                    average=average,
                )
            )
            description = T(
                "{matches} matchs renseignés sur {count}. La moyenne exclut les "
                "données absentes, pas les zéros.",
                matches=statistic.matches,
                count=len(rows),
            )
            self.values[field].setToolTip(description)
            tooltip(self.cards[field], description)
