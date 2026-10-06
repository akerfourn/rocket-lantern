"""Reusable session statistics cards with explicit missing-data coverage."""

from collections.abc import Sequence
from sqlite3 import Row

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from rl_winloose.statistics import STAT_LABELS, aggregate_statistics


class StatisticsPanel(QWidget):
    """Show totals, observed per-match averages and coverage for one player."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.values: dict[str, QLabel] = {}
        self.averages: dict[str, QLabel] = {}
        self.setStyleSheet(
            "QFrame#statCard { background: palette(base); border-radius: 6px; }"
            "QLabel#statValue { font-size: 21px; font-weight: 600; }"
        )
        for index, (field, title) in enumerate(STAT_LABELS.items()):
            card = QFrame()
            card.setObjectName("statCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(2)
            card_layout.addWidget(QLabel(title))
            self.values[field] = QLabel("—")
            self.values[field].setObjectName("statValue")
            card_layout.addWidget(self.values[field])
            self.averages[field] = QLabel("— / match · 0/0")
            card_layout.addWidget(self.averages[field])
            grid.addWidget(card, index // 4, index % 4)
            grid.setColumnStretch(index % 4, 1)
        layout.addLayout(grid)
        self.coverage = QLabel()
        self.coverage.setWordWrap(True)
        layout.addWidget(self.coverage)

    def update_rows(self, rows: Sequence[Row]) -> None:
        """Use all filtered matches, not only the visible history rows."""
        for field, statistic in aggregate_statistics(rows).items():
            value = "—"
            if statistic.total is not None:
                value = str(statistic.total)
            average = "—"
            if statistic.average is not None:
                average = f"{statistic.average:.1f}"
            self.values[field].setText(value)
            self.averages[field].setText(f"{average} / match · {statistic.matches}/{len(rows)}")
            self.averages[field].setToolTip(
                f"{statistic.matches} matchs renseignés sur {len(rows)}. "
                "La moyenne exclut les données absentes, pas les zéros."
            )
        final_matches = sum(bool(row["final_observed"]) for row in rows)
        self.coverage.setText(
            f"{len(rows)} matchs · {final_matches} états de fin reçus · "
            "Totaux observés ; moyennes sur les matchs renseignés (x/y)."
        )
        self.coverage.setToolTip(
            "Les compteurs peuvent être partiels, même avec un état de fin si un joueur "
            "est parti avant. — : donnée absente ; 0 : zéro reçu. "
            "Les résultats inconnus sont inclus dans ces statistiques."
        )
