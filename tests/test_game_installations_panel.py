"""Manual discovery and folder opening use controlled detectors and Qt signals."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_installations import DiscoveryReport, GameInstallation
from rocket_lantern.game_installations_panel import DiscoveryTask, GameInstallationsPanel
from rocket_lantern.i18n import language_manager


@pytest.fixture
def panel(application: QApplication) -> Iterator[GameInstallationsPanel]:
    language_manager().set_language("fr")
    widget = GameInstallationsPanel(detector=Mock(return_value=DiscoveryReport()))
    widget.show()
    yield widget
    widget.close()
    language_manager().set_language("fr")


def test_panel_should_scan_only_on_click_and_prevent_overlapping_searches(
    panel: GameInstallationsPanel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = Mock(spec=QThreadPool)
    monkeypatch.setattr(
        "rocket_lantern.game_installations_panel.QThreadPool.globalInstance", lambda: pool
    )
    detector = Mock(return_value=DiscoveryReport())
    panel.detector = detector

    assert not panel.open_button.isEnabled()
    panel.hide()
    panel.show()
    detector.assert_not_called()
    panel.detect_button.click()
    panel._detect()

    assert not panel.detect_button.isEnabled()
    pool.start.assert_called_once()
    detector.assert_not_called()
    task = pool.start.call_args.args[0]
    task.run()
    detector.assert_called_once_with()
    assert panel.detect_button.isEnabled()
    assert panel.status.text() == "Aucune installation de Rocket League trouvée."


def test_panel_should_allow_selection_and_open_only_selected_configuration_folder(
    panel: GameInstallationsPanel,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = GameInstallation("Steam", tmp_path / "Steam game", None)
    second = GameInstallation("Epic Games", tmp_path / "Epic game", None)
    second.config_directory.mkdir(parents=True)
    opener = Mock(return_value=True)
    monkeypatch.setattr("rocket_lantern.game_installations_panel.QDesktopServices.openUrl", opener)
    panel._completed(DiscoveryReport((first, second)))
    panel.selector.setCurrentIndex(1)
    panel.open_button.click()

    assert panel.selector.isVisible()
    assert panel.directory.text() == str(second.config_directory)
    assert panel.file.text() == "Aucun fichier Stats API trouvé dans ce dossier."
    opener.assert_called_once()
    assert Path(opener.call_args.args[0].toLocalFile()) == second.config_directory


def test_panel_should_not_launch_explorer_when_detected_folder_has_disappeared(
    panel: GameInstallationsPanel,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = Mock()
    monkeypatch.setattr("rocket_lantern.game_installations_panel.QDesktopServices.openUrl", opener)
    panel._completed(DiscoveryReport((GameInstallation("Steam", tmp_path / "missing", None),)))
    panel.open_button.click()

    opener.assert_not_called()
    assert "Relancez la détection" in panel.status.text()


def test_panel_should_translate_results_without_searching_again(
    panel: GameInstallationsPanel,
    application: QApplication,
    tmp_path: Path,
) -> None:
    detector = Mock()
    panel.detector = detector
    game = GameInstallation("Steam", tmp_path / "Victoire", tmp_path / "TAStatsAPI.ini")
    panel._completed(DiscoveryReport((game,), warnings=1))

    language_manager().set_language("en")
    application.processEvents()

    assert panel.title() == "Rocket League configuration"
    assert panel.detect_button.text() == "Detect installations"
    assert panel.open_button.text() == "Open folder"
    assert panel.status.text().startswith("Installations found: 1")
    assert "results may be incomplete" in panel.status.text()
    assert panel.file.text() == "File to configure: TAStatsAPI.ini"
    assert "Victoire" in panel.directory.text()
    detector.assert_not_called()


def test_worker_should_deliver_background_results_to_panel(
    panel: GameInstallationsPanel,
    application: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel.detector = Mock(return_value=DiscoveryReport(warnings=1))
    pool = QThreadPool()
    monkeypatch.setattr(
        "rocket_lantern.game_installations_panel.QThreadPool.globalInstance", lambda: pool
    )

    panel.detect_button.click()
    panel.hide()
    assert pool.waitForDone(5000)
    application.processEvents()

    assert "sources sont illisibles" in panel.status.text()
    assert not panel.isVisible()
    assert panel.detect_button.isEnabled()


def test_worker_should_finish_safely_after_panel_is_destroyed(application: QApplication) -> None:
    widget = GameInstallationsPanel(detector=Mock())
    task = DiscoveryTask(Mock(return_value=DiscoveryReport()))
    task.signals.completed.connect(widget._completed)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    task.run()


def test_worker_should_report_failure_and_reenable_detection(panel: GameInstallationsPanel) -> None:
    panel.detect_button.setEnabled(False)
    task = DiscoveryTask(Mock(side_effect=OSError("synthetic failure")))
    task.signals.failed.connect(panel._failed)

    task.run()

    assert panel.detect_button.isEnabled()
    assert panel.status.text() == "Impossible de rechercher les installations. Réessayez."
