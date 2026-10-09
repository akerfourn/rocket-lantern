"""Prominent filtered W/L summary with resolution-independent outcome symbols."""

from typing import Literal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout

from rocket_lantern.i18n import text as T
from rocket_lantern.storage import Summary
from rocket_lantern.translated_widgets import TranslatedLabel as QLabel
from rocket_lantern.translated_widgets import binding


def outcome_icon(outcome: Literal["win", "loss"]) -> QIcon:
    """Draw a check or cross; shape and text distinguish outcomes beyond color."""
    pixmap = QPixmap(56, 56)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#23834a")
        background = QColor("#e2f4e8")
        if outcome == "loss":
            color = QColor("#b54242")
            background = QColor("#fae6e6")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawEllipse(QRectF(1, 1, 26, 26))
        painter.setPen(QPen(color, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if outcome == "win":
            painter.drawLine(QPointF(7, 14), QPointF(12, 19))
            painter.drawLine(QPointF(12, 19), QPointF(21, 9))
        else:
            painter.drawLine(QPointF(9, 9), QPointF(19, 19))
            painter.drawLine(QPointF(19, 9), QPointF(9, 19))
    finally:
        painter.end()
    return QIcon(pixmap)


def balance_icon(balance: int) -> QIcon:
    """Distinguish positive, negative and even balances with an arrow or equals sign."""
    color = QColor("#617083")
    background = QColor("#eaf0f5")
    if balance > 0:
        color = QColor("#23834a")
        background = QColor("#e2f4e8")
    elif balance < 0:
        color = QColor("#b54242")
        background = QColor("#fae6e6")
    pixmap = QPixmap(56, 56)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawEllipse(QRectF(1, 1, 26, 26))
        painter.setPen(QPen(color, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if balance == 0:
            painter.drawLine(QPointF(9, 11), QPointF(19, 11))
            painter.drawLine(QPointF(9, 17), QPointF(19, 17))
        else:
            tip = 8
            shoulder = 13
            if balance < 0:
                tip = 20
                shoulder = 15
            painter.drawLine(QPointF(14, 8), QPointF(14, 20))
            painter.drawLine(QPointF(9, shoulder), QPointF(14, tip))
            painter.drawLine(QPointF(19, shoulder), QPointF(14, tip))
    finally:
        painter.end()
    return QIcon(pixmap)


class ResultSummary(QFrame):
    """Keep filtered counts and their scope visible independently of the active tab."""

    def __init__(self) -> None:
        super().__init__()
        self._summary = Summary(0, 0, 0)
        self.setObjectName("resultSummary")
        self.setStyleSheet(
            "QFrame#resultSummary { background: palette(base); border-radius: 8px; }"
            "QLabel#outcomeCount { font-size: 23px; font-weight: 600; }"
            "QLabel#winRate { font-size: 20px; font-weight: 600; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        self.context = QLabel(T("Bilan · session actuelle"))
        self.context.setTextFormat(Qt.TextFormat.PlainText)
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        counts = QHBoxLayout()
        counts.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        counts.setSpacing(12)
        self.wins = self._outcome_count(counts, "win")
        counts.addSpacing(12)
        self.losses = self._outcome_count(counts, "loss")
        counts.addSpacing(12)
        self._balance_icons = {value: balance_icon(value) for value in (-1, 0, 1)}
        self.balance_symbol = QLabel()
        self.balance_symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.balance_symbol.setFixedSize(28, 28)
        counts.addWidget(self.balance_symbol)
        self.balance = QLabel()
        self.balance.setObjectName("outcomeCount")
        self.balance.setToolTip(T("Delta W/L : victoires moins défaites."))
        counts.addWidget(self.balance)
        for count in (self.wins, self.losses, self.balance):
            count.ensurePolished()
            count.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            # Use one line box, independent of the digits and their descenders.
            count.setFixedHeight(max(28, count.fontMetrics().height()))
        counts.addStretch()
        self.rate = QLabel()
        self.rate.setObjectName("winRate")
        counts.addWidget(self.rate)
        self.unknown = QLabel()
        counts.addWidget(self.unknown)
        layout.addLayout(counts)
        binding(self).callbacks.append(self._update_accessibility)
        self.set_summary(self._summary)

    @staticmethod
    def _outcome_count(layout: QHBoxLayout, outcome: Literal["win", "loss"]) -> QLabel:
        symbol = QLabel()
        symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        symbol.setPixmap(outcome_icon(outcome).pixmap(28, 28))
        symbol.setFixedSize(28, 28)
        layout.addWidget(symbol)
        count = QLabel()
        count.setObjectName("outcomeCount")
        layout.addWidget(count)
        return count

    def set_summary(self, summary: Summary) -> None:
        """Update only persisted filtered results, never the unfinished live score."""
        self._summary = summary
        balance = summary.wins - summary.losses
        balance_text = str(balance)
        direction = 0
        description = T("Bilan équilibré")
        if balance > 0:
            balance_text = f"+{balance}"
            direction = 1
            description = T("Bilan positif")
        elif balance < 0:
            direction = -1
            description = T("Bilan négatif")
        self.wins.setText(T("{wins} victoires", wins=summary.wins))
        self.losses.setText(T("{losses} défaites", losses=summary.losses))
        self.balance.setText(balance_text)
        self.balance_symbol.setPixmap(self._balance_icons[direction].pixmap(28, 28))
        self.balance_symbol.setAccessibleName(description)
        self.balance_symbol.setToolTip(description)
        self.rate.setText(T("{win_rate:.1f} % de victoires", win_rate=summary.win_rate))
        self.unknown.setText(T("{unknown} inconnus", unknown=summary.unknown))
        self._update_accessibility()

    def _update_accessibility(self) -> None:
        """Keep screen-reader output in the same language as the visible counts."""
        balance = self._summary.wins - self._summary.losses
        balance_text = str(balance)
        if balance > 0:
            balance_text = f"+{balance}"
        self.setAccessibleName(
            str(T("{wins} victoires", wins=self._summary.wins))
            + "    "
            + str(T("{losses} défaites", losses=self._summary.losses))
            + f" {balance_text}    "
            + str(T("{win_rate:.1f} % de victoires", win_rate=self._summary.win_rate))
            + "    "
            + str(T("{unknown} inconnus", unknown=self._summary.unknown))
        )

    def text(self) -> str:
        """Expose a readable aggregate for accessibility and diagnostics."""
        return (
            f"{self.wins.text()}    {self.losses.text()} {self.balance.text()}    "
            f"{self.rate.text()}    {self.unknown.text()}"
        )
