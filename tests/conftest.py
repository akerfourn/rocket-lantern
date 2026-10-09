"""Shared offscreen Qt application; no real game or network is used."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from rocket_lantern.i18n import language_manager


@pytest.fixture(scope="session")
def application() -> Iterator[QApplication]:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test", "-platform", "offscreen"])
    language_manager().set_language("fr")
    yield app
