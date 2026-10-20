"""Cheap release gates, fail-fast checks and tag-local validation before dependency setup."""

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/windows-build.yml"


def job_contents(name: str) -> str:
    contents = WORKFLOW.read_text(encoding="utf-8")
    lines = contents.split(f"\n  {name}:\n", 1)[1].splitlines()
    result: list[str] = []
    for line in lines:
        if line and not line.startswith("    "):
            break
        result.append(line)
    return "\n".join(result)


def step_commands(name: str) -> str:
    contents = job_contents("prepare")
    section = contents.split(f"      - name: {name}\n", 1)[1]
    commands = section.split("        run: |\n", 1)[1]
    result: list[str] = []
    for line in commands.splitlines():
        if line and not line.startswith("          "):
            break
        result.append(line[10:])
    return "\n".join(result)


def run_preflight(
    step: str, directory: Path, variables: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("pwsh")
    if executable is None and sys.platform == "win32":
        executable = shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is required to execute the actual preflight steps")
    environment = os.environ.copy()
    environment.update(variables)
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    environment["GITHUB_OUTPUT"] = str(directory / "outputs")
    commands = "$ErrorActionPreference = 'Stop'\n" + step_commands(step)
    encoded = base64.b64encode(commands.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


@pytest.mark.parametrize(
    "reference,requested,stable",
    [
        ("main", "", False),
        ("v1.2.3", "", True),
        ("v1.2.3-alpha.1", "", False),
        ("main", "v1.2.3", True),
    ],
)
def test_preflight_should_identify_only_stable_tags_without_installing_dependencies(
    tmp_path: Path, reference: str, requested: str, stable: bool
) -> None:
    kind = "branch"
    if reference.startswith("v"):
        kind = "tag"
    result = run_preflight(
        "Identify stable version tag",
        tmp_path,
        {"GITHUB_REF_TYPE": kind, "GITHUB_REF_NAME": reference, "REQUESTED_TAG": requested},
    )

    assert result.returncode == 0, result.stderr
    outputs = (tmp_path / "outputs").read_text(encoding="utf-8")
    assert f"stable={str(stable).lower()}" in outputs
    assert not (tmp_path / ".venv").exists()


def test_preflight_should_reject_invalid_manual_tag_before_dependency_installation(
    tmp_path: Path,
) -> None:
    result = run_preflight(
        "Identify stable version tag",
        tmp_path,
        {"REQUESTED_TAG": "v1.2.3-alpha.1", "GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": "main"},
    )

    assert result.returncode != 0
    assert "stable vMAJOR.MINOR.PATCH" in result.stderr


@pytest.mark.parametrize(
    "version,tag,preview,notes,error",
    [
        ("1.2.3", "v1.2.3", False, "Release notes.", ""),
        ("1.2.3-alpha.1", "v1.2.3-alpha.1", True, "Preview notes.", ""),
        ("1.2.3", "v1.2.4", False, "Release notes.", "Version tag must match"),
        ("1.2.3", "v1.2.3", False, None, "Missing release notes"),
        ("1.2.3", "v1.2.3", False, "  \n", "Empty release notes"),
        ("1.2.3-beta.2", "v1.2.3-beta.2", True, None, "Missing release notes"),
    ],
)
def test_preflight_should_validate_version_and_tag_local_notes_without_project_dependencies(
    tmp_path: Path, version: str, tag: str, preview: bool, notes: str | None, error: str
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    if notes is not None:
        filename = f"release-{version}.md"
        if preview:
            filename = "prerelease.md"
        directory = tmp_path / "releases"
        directory.mkdir()
        (directory / filename).write_text(notes, encoding="utf-8")

    result = run_preflight(
        "Validate release inputs",
        tmp_path,
        {"RELEASE_TAG": tag, "PRERELEASE": str(preview).lower()},
    )

    if error:
        assert result.returncode != 0
        assert error in result.stderr
    else:
        assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".venv").exists()


def test_workflow_should_gate_expensive_checks_and_keep_preflight_dependency_free() -> None:
    prepare = job_contents("prepare")
    checks = job_contents("checks")

    assert "runs-on: ubuntu-latest" in prepare
    assert "setup-uv" not in prepare
    assert "uv sync" not in prepare and "pytest" not in prepare
    assert "run: python scripts/detect-prerelease.py" in prepare
    assert "ref: ${{ inputs.release_tag || github.sha }}" in prepare
    assert "needs: prepare" in checks
    assert "needs.prepare.outputs.publish == 'true' ||" in checks
    assert "github.event_name == 'pull_request' ||" in checks
    assert "github.event_name == 'workflow_dispatch'" in checks
    assert "publish: ${{ needs.prepare.outputs.publish }}" in checks
    assert "ref: ${{ inputs.release_tag || github.sha }}" in checks


def test_workflow_should_run_lint_before_tests_and_stop_on_first_test_failure() -> None:
    checks = job_contents("checks")

    assert checks.index("Lint and formatting") < checks.index("Compile translations")
    assert checks.index("Compile translations") < checks.index("Run tests")
    assert "pytest -x -v" in checks
    assert "--junitxml=build/test-results.xml" in checks
    assert "if: always()" in checks and "name: test-results" in checks


def test_workflow_should_cancel_superseded_pr_checks_without_cancelling_release_checks() -> None:
    checks = job_contents("checks")

    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in checks
    assert "format('pr-{0}', github.event.pull_request.number)" in checks
    assert "format('run-{0}', github.run_id)" in checks
    assert "cancel-in-progress: false" in job_contents("release")
    assert "concurrency:" not in WORKFLOW.read_text(encoding="utf-8").split("jobs:", 1)[0]


def test_workflow_should_limit_pushes_to_version_inputs_and_validate_code_changes_on_prs() -> None:
    triggers = WORKFLOW.read_text(encoding="utf-8").split("permissions:", 1)[0]
    push = triggers.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
    pull_request = triggers.split("  pull_request:\n", 1)[1].split("  workflow_dispatch:\n", 1)[0]

    assert 'branches: ["**"]' in push and 'tags: ["v*"]' in push
    assert "- pyproject.toml" in push
    assert "- src/**" not in push and "- docs/**" not in push
    for path in ("src/**", "tests/**", "packaging/**", "scripts/**", "uv.lock", ".github/**"):
        assert f"- {path}" in pull_request
    assert "- docs/**" not in pull_request and "- README.md" not in pull_request
