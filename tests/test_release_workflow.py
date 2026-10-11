"""Exercise publication commands with a fake GitHub CLI and local packages."""

import os
import re
import runpy
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from unittest.mock import Mock

import pytest

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/windows-build.yml"


def publication_script() -> str:
    """Read the actual final workflow step rather than copying its commands."""
    contents = WORKFLOW.read_text(encoding="utf-8")
    section = contents.split("      - name: Publish GitHub release\n", 1)[1]
    commands = section.split("        run: |\n", 1)[1]
    return "\n".join(line[10:] for line in commands.splitlines() if line.startswith("          "))


def bash_executable() -> str:
    if sys.platform == "win32":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    executable = shutil.which("bash")
    if executable is None:
        pytest.skip("Bash is required to exercise the GitHub publication script")
    return executable


def run_publication(
    directory: Path,
    *,
    exists: bool = False,
    preview: bool = False,
    preview_version: str = "1.2.3-beta.1",
    package_version: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Intercept all gh calls; never contact GitHub or use real credentials."""
    environment = os.environ.copy()
    environment["RELEASE_TAG"] = "v1.2.3"
    environment["RELEASE_EXISTS"] = "true" if exists else "false"
    environment["PRERELEASE"] = "true" if preview else "false"
    environment["RELEASE_COMMIT"] = "abc123"
    if preview:
        environment["RELEASE_TAG"] = f"v{preview_version}"
    environment["PACKAGE_VERSION"] = package_version or environment["RELEASE_TAG"].removeprefix("v")
    fake_cli = """
gh() {
  if [ "$1 $2" = 'release view' ]; then
    [ "$RELEASE_EXISTS" = true ]
    return
  fi
  printf 'gh'
  printf ' <%s>' "$@"
  printf '\\n'
}
"""
    return subprocess.run(
        [bash_executable(), "--noprofile", "--norc", "-c", fake_cli + publication_script()],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def prepare_packages(directory: Path) -> None:
    notes = directory / "releases/release-1.2.3.md"
    notes.parent.mkdir()
    notes.write_text("# Release 1.2.3\n\nTest notes.\n", encoding="utf-8")
    packages = directory / "dist/installers"
    packages.mkdir(parents=True)
    for suffix in ("setup.exe", "portable.zip"):
        (packages / f"RocketLantern-1.2.3-windows-x64-{suffix}").write_bytes(b"test package")


def test_publication_should_create_release_with_notes_and_both_packages_when_absent(
    tmp_path: Path,
) -> None:
    prepare_packages(tmp_path)
    result = run_publication(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "<release> <create> <v1.2.3>" in result.stdout
    assert "<--verify-tag>" in result.stdout
    assert "<--notes-file> <releases/release-1.2.3.md>" in result.stdout
    assert "<dist/installers/RocketLantern-1.2.3-windows-x64-setup.exe>" in result.stdout
    assert "<dist/installers/RocketLantern-1.2.3-windows-x64-portable.zip>" in result.stdout


def test_publication_should_update_same_release_when_rerun(tmp_path: Path) -> None:
    prepare_packages(tmp_path)
    result = run_publication(tmp_path, exists=True)

    assert result.returncode == 0, result.stderr
    assert "<release> <create>" not in result.stdout
    assert "<release> <upload> <v1.2.3>" in result.stdout
    assert "<--clobber>" in result.stdout
    assert "<release> <edit> <v1.2.3>" in result.stdout
    assert "<--notes-file> <releases/release-1.2.3.md>" in result.stdout
    assert "<--draft=false> <--prerelease=false>" in result.stdout


def test_publication_should_stop_before_github_when_notes_are_missing(tmp_path: Path) -> None:
    result = run_publication(tmp_path)

    assert result.returncode != 0
    assert result.stdout == "", "No publication command may run without notes and packages"


def test_publication_should_stop_before_github_when_package_is_missing(tmp_path: Path) -> None:
    prepare_packages(tmp_path)
    (tmp_path / "dist/installers/RocketLantern-1.2.3-windows-x64-portable.zip").unlink()
    result = run_publication(tmp_path)

    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize("tag", ["v1.0.0", "v2.12.34"])
def test_workflow_should_accept_stable_tag_for_publication(tag: str) -> None:
    pattern = re.search(r"\$pattern = '([^']+)'", WORKFLOW.read_text(encoding="utf-8"))
    assert pattern is not None
    assert re.fullmatch(pattern[1], tag) is not None


@pytest.mark.parametrize("tag", ["main", "v1.0.0-alpha.1", "v1.0.0-beta.1", "v1.0.0-rc.1"])
def test_workflow_should_exclude_nonstable_reference_from_publication(tag: str) -> None:
    pattern = re.search(r"\$pattern = '([^']+)'", WORKFLOW.read_text(encoding="utf-8"))
    assert pattern is not None
    assert re.fullmatch(pattern[1], tag) is None


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        ("1.2.3-beta.1", "1.2.3", "v1.2.3-beta.1"),
        ("1.2.3rc2", "1.2.3rc1", "v1.2.3rc2"),
        ("1.2.3-alpha.1", "1.2.3-alpha.1", ""),
        ("1.2.3", "1.2.3rc2", ""),
        ("1.2.3.post1", "1.2.3", ""),
    ],
)
def test_detection_should_only_publish_changed_prerelease(
    current: str, previous: str, expected: str
) -> None:
    detector = runpy.run_path(str(WORKFLOW.parents[2] / "scripts/detect-prerelease.py"))
    assert detector["prerelease_tag"](current, previous) == expected


@pytest.mark.parametrize("exists", [False, True])
def test_publication_should_keep_preview_separate_from_latest_stable(
    tmp_path: Path, exists: bool
) -> None:
    prepare_packages(tmp_path)
    (tmp_path / "releases/prerelease.md").write_text("Preview notes.", encoding="utf-8")
    for package in (tmp_path / "dist/installers").iterdir():
        package.rename(package.with_name(package.name.replace("1.2.3-", "1.2.3-beta.1-")))

    result = run_publication(tmp_path, exists=exists, preview=True)

    assert result.returncode == 0, result.stderr
    assert "<--notes-file> <releases/prerelease.md>" in result.stdout
    assert "<--latest=false>" in result.stdout
    assert "RocketLantern-1.2.3-beta.1-windows-x64-setup.exe" in result.stdout
    if exists:
        assert "<--prerelease=true>" in result.stdout
    else:
        assert "<--target> <abc123> <--prerelease>" in result.stdout
        assert "<--verify-tag>" not in result.stdout


@pytest.mark.parametrize("package_version", ["1.1.0-alpha.1", "1.1.0a1", "1.1.0-rc.2"])
def test_publication_should_use_exact_version_emitted_by_windows_build(
    tmp_path: Path, package_version: str
) -> None:
    prepare_packages(tmp_path)
    (tmp_path / "releases/prerelease.md").write_text("Preview notes.", encoding="utf-8")
    for package in (tmp_path / "dist/installers").iterdir():
        package.rename(package.with_name(package.name.replace("1.2.3-", f"{package_version}-")))
    result = run_publication(
        tmp_path, preview=True, preview_version="1.1.0-alpha.1", package_version=package_version
    )
    assert result.returncode == 0, result.stderr
    assert f"RocketLantern-{package_version}-windows-x64-setup.exe" in result.stdout


def test_publication_should_accept_names_from_actual_project_metadata(tmp_path: Path) -> None:
    actual_version = version("rocket-lantern")
    prepare_packages(tmp_path)
    (tmp_path / "releases/prerelease.md").write_text("Preview notes.", encoding="utf-8")
    for package in (tmp_path / "dist/installers").iterdir():
        package.rename(package.with_name(package.name.replace("1.2.3-", f"{actual_version}-")))
    result = run_publication(
        tmp_path, preview=True, preview_version=actual_version, package_version=actual_version
    )
    assert result.returncode == 0, result.stderr


def test_publication_should_explain_missing_file_before_contacting_github(tmp_path: Path) -> None:
    result = run_publication(tmp_path)
    assert result.returncode != 0
    assert "Missing or empty release input:" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("event", "reference", "previous", "current", "publishes"),
    [
        ("push", "branch", "1.1.0-alpha.0", "1.1.0-alpha.1", True),
        ("push", "branch", "1.1.0-alpha.1", "1.1.0-alpha.1", False),
        ("push", "branch", "1.1.0-alpha.1", "1.1.0", False),
        ("pull_request", "branch", "1.1.0-alpha.0", "1.1.0-alpha.1", False),
        ("push", "tag", "1.1.0-alpha.0", "1.1.0-alpha.1", False),
    ],
)
def test_detection_should_emit_actual_job_outputs_only_for_changed_branch_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    event: str,
    reference: str,
    previous: str,
    current: str,
    publishes: bool,
) -> None:
    detector = runpy.run_path(str(WORKFLOW.parents[2] / "scripts/detect-prerelease.py"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nversion = "{current}"\n', encoding="utf-8"
    )
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_REF_TYPE", reference)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("PUSH_BEFORE", "a" * 40)
    previous_file = subprocess.CompletedProcess(
        [], 0, stdout=f'[project]\nversion = "{previous}"\n'
    )
    monkeypatch.setattr(subprocess, "run", Mock(return_value=previous_file))
    detector["main"]()
    if publishes:
        assert (
            output.read_text(encoding="utf-8") == f"publish=true\nprerelease=true\ntag=v{current}\n"
        )
    else:
        assert not output.exists()


def test_workflow_should_transfer_exact_build_version_to_publication() -> None:
    contents = WORKFLOW.read_text(encoding="utf-8")
    assert "package_version: ${{ steps.version.outputs.package_version }}" in contents
    assert "PACKAGE_VERSION: ${{ needs.windows.outputs.package_version }}" in contents
    assert 'package_version="${PACKAGE_VERSION:?' in contents
    assert "re.sub" not in publication_script()


def test_workflow_should_upload_only_the_exact_packages_it_validated() -> None:
    contents = WORKFLOW.read_text(encoding="utf-8")
    assert (
        "RocketLantern-${{ steps.version.outputs.package_version }}-windows-x64-setup.exe"
        in contents
    )
    assert (
        "RocketLantern-${{ steps.version.outputs.package_version }}-windows-x64-portable.zip"
        in contents
    )
    assert "path: dist/installers/RocketLantern-*" not in contents


def test_workflow_should_keep_manual_rebuild_compatible_with_older_stable_tags() -> None:
    contents = WORKFLOW.read_text(encoding="utf-8")
    assert "if (Test-Path scripts/test-windows-packages.ps1)" in contents
    assert "Existing stable tags predate the shared validation script." in contents
