"""Configuration checks and per-installation updates never touch real game files."""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication

from rocket_lantern.game_installations import DiscoveryReport, GameInstallation
from rocket_lantern.game_installations_panel import (
    ConfigurationCheck,
    DiscoveryTask,
    GameInstallationsPanel,
)
from rocket_lantern.i18n import language_manager
from rocket_lantern.packet_configuration import RateConfiguration, read_configuration


@pytest.fixture
def panel(application: QApplication) -> Iterator[GameInstallationsPanel]:
    language_manager().set_language("fr")
    widget = GameInstallationsPanel(detector=Mock(return_value=DiscoveryReport()))
    widget.show()
    yield widget
    widget.close()
    language_manager().set_language("fr")


def configuration(tmp_path: Path, name: str, rate: int) -> RateConfiguration:
    directory = tmp_path / name
    path = directory / "TAGame/Config/DefaultStatsAPI.ini"
    path.parent.mkdir(parents=True)
    path.write_text(
        f"[TAGame.MatchStatsExporter_TA]\nPacketSendRate={rate}\nWebPort=49124\n", encoding="utf-8"
    )
    installation = GameInstallation(name, directory, path)
    return read_configuration(installation)


def show_configurations(panel: GameInstallationsPanel, *checked: RateConfiguration) -> None:
    report = DiscoveryReport(tuple(item.installation for item in checked))
    panel._completed(ConfigurationCheck(report, checked))


def queue_tasks(monkeypatch: pytest.MonkeyPatch) -> Mock:
    pool = Mock(spec=QThreadPool)
    monkeypatch.setattr(
        "rocket_lantern.game_installations_panel.QThreadPool.globalInstance", lambda: pool
    )
    return pool


def test_panel_should_check_only_on_click_and_prevent_overlapping_searches(
    panel: GameInstallationsPanel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = queue_tasks(monkeypatch)
    detector = Mock(return_value=DiscoveryReport())
    panel.detector = detector
    panel.hide()
    panel.show()
    detector.assert_not_called()

    panel.detect_button.click()
    panel._detect()

    assert not panel.detect_button.isEnabled()
    pool.start.assert_called_once()
    detector.assert_not_called()
    pool.start.call_args.args[0].run()
    detector.assert_called_once_with()
    assert panel.detect_button.isEnabled()
    assert panel.status.text() == "Aucune installation de Rocket League trouvée."


def test_panel_should_distinguish_low_matching_and_high_rates_for_each_installation(
    panel: GameInstallationsPanel,
    tmp_path: Path,
) -> None:
    show_configurations(
        panel,
        configuration(tmp_path, "Steam", 1),
        configuration(tmp_path, "Epic", 10),
        configuration(tmp_path, "Other Steam", 60),
    )

    low, matching, high = panel.rows
    assert "inférieur au réglage" in low.status.text()
    assert "#c87518" in low.status.styleSheet()
    assert low.apply_button.isEnabled()
    assert "conforme" in matching.status.text()
    assert not matching.apply_button.isEnabled()
    assert "cadence suffisante" in high.status.text()
    assert "#408fc4" in high.status.styleSheet()
    assert high.apply_button.isEnabled()


def test_panel_should_recompare_desired_rate_without_reading_or_writing_again(
    panel: GameInstallationsPanel,
    tmp_path: Path,
) -> None:
    checked = configuration(tmp_path, "Steam", 10)
    panel.detector = Mock()
    show_configurations(panel, checked)

    panel.packet_rate.setValue(20)

    assert "inférieur au réglage" in panel.rows[0].status.text()
    assert panel.rows[0].apply_button.text() == "Appliquer 20"
    assert checked.document.path.read_bytes() == checked.document.contents
    panel.detector.assert_not_called()


def test_panel_should_apply_only_the_clicked_installation_and_refresh_its_status(
    panel: GameInstallationsPanel,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = configuration(tmp_path, "Steam", 1)
    second = configuration(tmp_path, "Epic", 60)
    show_configurations(panel, first, second)
    pool = queue_tasks(monkeypatch)

    panel.rows[0].apply_button.click()
    assert not panel.packet_rate.isEnabled()
    assert all(not row.apply_button.isEnabled() for row in panel.rows)
    pool.start.call_args.args[0].run()

    assert panel.rows[0].configuration.rate == 10
    assert not panel.rows[0].apply_button.isEnabled()
    assert panel.rows[1].configuration.rate == 60
    assert second.document.path.read_bytes() == second.document.contents
    assert (
        first.document.path.with_name(first.document.path.name + ".rocketlantern.bak").read_bytes()
        == first.document.contents
    )
    assert "Réglage appliqué" in panel.status.text()


def test_panel_should_reenable_actions_and_require_recheck_on_external_edits(
    panel: GameInstallationsPanel,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked = configuration(tmp_path, "Steam", 1)
    show_configurations(panel, checked)
    checked.document.path.write_text(
        "[TAGame.MatchStatsExporter_TA]\nPacketSendRate=5\n", encoding="utf-8"
    )
    pool = queue_tasks(monkeypatch)

    panel.rows[0].apply_button.click()
    pool.start.call_args.args[0].run()

    assert "Le fichier a changé" in panel.status.text()
    assert panel.packet_rate.isEnabled()
    assert read_configuration(checked.installation).rate == 5


def test_panel_should_open_only_the_clicked_configuration_folder(
    panel: GameInstallationsPanel,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = configuration(tmp_path, "Steam", 1)
    second = configuration(tmp_path, "Epic", 60)
    show_configurations(panel, first, second)
    opener = Mock(return_value=True)
    monkeypatch.setattr("rocket_lantern.packet_rate_row.QDesktopServices.openUrl", opener)

    panel.rows[1].open_button.click()

    opener.assert_called_once()
    assert Path(opener.call_args.args[0].toLocalFile()) == second.installation.config_directory


def test_panel_should_translate_results_without_rechecking_or_writing(
    panel: GameInstallationsPanel,
    application: QApplication,
    tmp_path: Path,
) -> None:
    checked = configuration(tmp_path, "Victoire", 60)
    panel.detector = Mock()
    show_configurations(panel, checked)

    language_manager().set_language("en")
    application.processEvents()

    assert panel.title() == "Rocket League configuration"
    assert panel.detect_button.text() == "Check configurations"
    assert panel.rows[0].apply_button.text() == "Apply 10"
    assert "sufficient update rate" in panel.rows[0].status.text()
    assert "Victoire" in panel.rows[0].directory.text()
    assert checked.document.path.read_bytes() == checked.document.contents
    panel.detector.assert_not_called()


def test_worker_should_finish_checks_when_panel_is_hidden(
    panel: GameInstallationsPanel,
    application: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked = configuration(tmp_path, "Steam", 1)
    panel.detector = Mock(return_value=DiscoveryReport((checked.installation,)))
    pool = QThreadPool()
    monkeypatch.setattr(
        "rocket_lantern.game_installations_panel.QThreadPool.globalInstance", lambda: pool
    )

    panel.detect_button.click()
    panel.hide()
    assert pool.waitForDone(5000)
    application.processEvents()

    assert len(panel.rows) == 1
    assert panel.rows[0].configuration.rate == 1
    assert not panel.isVisible()
    assert panel.detect_button.isEnabled()


def test_worker_should_finish_safely_after_panel_is_destroyed(application: QApplication) -> None:
    widget = GameInstallationsPanel(detector=Mock())
    task = DiscoveryTask(Mock(return_value=DiscoveryReport()))
    task.signals.completed.connect(widget._completed)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    task.run()


def test_worker_should_report_failure_and_reenable_check(panel: GameInstallationsPanel) -> None:
    panel.detect_button.setEnabled(False)
    task = DiscoveryTask(Mock(side_effect=OSError("synthetic failure")))
    task.signals.failed.connect(panel._check_failed)

    task.run()

    assert panel.detect_button.isEnabled()
    assert panel.status.text() == "Impossible de rechercher les installations. Réessayez."
