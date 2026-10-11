"""Guard the installer cleanup scope and bundled version validation."""

import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[1]


def test_installer_should_remove_only_app_metadata_before_copying_new_files() -> None:
    contents = (ROOT / "packaging/windows/installer.iss").read_text(encoding="utf-8")
    section = contents.split("[InstallDelete]\n", 1)[1].split("\n[", 1)[0]
    directives = [line for line in section.splitlines() if line and not line.startswith(";")]

    assert directives == [
        'Type: filesandordirs; Name: "{app}\\_internal\\rocket_lantern-*.dist-info"'
    ]


def test_smoke_test_should_reject_old_metadata_before_starting_qt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = runpy.run_path(str(ROOT / "packaging/windows/launcher.py"))
    smoke_test = launcher["smoke_test"]
    application = Mock()
    monkeypatch.setitem(smoke_test.__globals__, "version", Mock(return_value="1.1.0-alpha.2"))
    monkeypatch.setitem(smoke_test.__globals__, "QApplication", application)

    with pytest.raises(
        RuntimeError,
        match=r"expected 1\.1\.0-alpha\.3, found 1\.1\.0-alpha\.2",
    ):
        smoke_test("1.1.0-alpha.3")

    application.assert_not_called()
