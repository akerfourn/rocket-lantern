"""Named live boost gauge with explicit low, empty and unavailable states."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from rocket_lantern.boost_bar import BoostBar


def boost_color(value: int | None) -> str:
    """Apply strict thresholds: 50 stays orange and 25 stays red."""
    if value is None:
        return "#617083"
    if value > 50:
        return "#23834a"
    if value > 25:
        return "#c87518"
    return "#b54242"


class BoostGauge(QWidget):
    """Keep the received number visible even when Qt hides indeterminate text."""

    def __init__(self, muted: bool = False) -> None:
        super().__init__()
        self._muted = muted
        self._color: str | None = None
        self.setMaximumWidth(240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.name = QLabel()
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.name, 1)
        self.bar = BoostBar()
        self.bar.setFixedHeight(22)
        self.bar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setToolTip(
            "Boost reçu : > 50 % vert ; > 25 % orange ; ≤ 25 % rouge. "
            "À 0 %, l’indicateur rouge est indéterminé ; — signifie champ non reçu."
        )
        self.amount = QLabel()
        self.amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.amount.setStyleSheet("font-weight: 600;")
        header.addWidget(self.amount)
        layout.addLayout(header)
        layout.addWidget(self.bar)
        self.set_boost("joueur sélectionné", None)

    def set_boost(self, name: str, value: int | None) -> None:
        """Update in place; never restart a busy indicator on identical zero packets."""
        self.name.setText(name)
        self.name.setToolTip(name)
        self.setFixedHeight(
            max(self.name.fontMetrics().height(), self.amount.fontMetrics().height())
            + 4
            + self.bar.height()
        )
        self.bar.setEnabled(value is not None)
        maximum = 100
        if value == 0 and not self._muted:
            maximum = 0
        if self.bar.maximum() != maximum:
            self.bar.setRange(0, maximum)
        self.bar.set_loading(value == 0 and not self._muted)
        if value is None:
            self.bar.setValue(0)
            self.bar.setFormat("— · champ non reçu")
            self.amount.setText("—")
            description = "champ non reçu"
        else:
            self.bar.setValue(value)
            self.bar.setFormat("%p %")
            self.amount.setText(f"{value} %")
            description = f"{value} %"
            if value == 0:
                self.amount.setText("0 % · vide")
                description = "0 % · boost vide"
        self.bar.setAccessibleName(f"Boost · {name} · {description}")
        self.amount.setToolTip(description)
        color = boost_color(value)
        if self._muted:
            color = "#7c838a"
        if color == self._color:
            return
        self._color = color
        self.bar.setStyleSheet(
            "QProgressBar { border: 1px solid palette(mid); border-radius: 4px; "
            "background: palette(alternate-base); min-height: 18px; }"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )
