"""Validate actual packages and dry-run publication without accessing GitHub."""

import argparse
import os
import subprocess
import sys
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from rocket_lantern.updates import version_key

ROOT = Path(__file__).resolve().parents[1]


def validate_packages(package_version: str) -> None:
    """Inspect real Windows packages, including the embedded app metadata."""
    packages = ROOT / "dist/installers"
    installer = packages / f"RocketLantern-{package_version}-windows-x64-setup.exe"
    with installer.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Installer is not a Windows executable")
    portable = packages / f"RocketLantern-{package_version}-windows-x64-portable.zip"
    with ZipFile(portable) as archive:
        if archive.testzip() is not None:
            raise ValueError("Portable archive contains corrupted data")
        executable = archive.read("RocketLantern/RocketLantern.exe")
        if executable != (ROOT / "dist/RocketLantern/RocketLantern.exe").read_bytes():
            raise ValueError("Portable executable differs from the built executable")
        metadata_paths = [
            path
            for path in archive.namelist()
            if "/rocket_lantern-" in path and path.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError("Portable archive must contain application version metadata")
        metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
        if metadata["Version"] != package_version:
            raise ValueError("Portable metadata version differs from package filenames")


def publication_commands() -> str:
    contents = (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
    section = contents.split("      - name: Publish GitHub release\n", 1)[1]
    commands = section.split("        run: |\n", 1)[1]
    return "\n".join(line[10:] for line in commands.splitlines() if line.startswith("          "))


def dry_run(package_version: str) -> None:
    """Run the real Bash script against real packages; intercept every gh call."""
    bash = "bash"
    if sys.platform == "win32":
        bash = "C:/Program Files/Git/bin/bash.exe"
    key = version_key(package_version)
    if key is None:
        raise ValueError("Unsupported package version")
    environment = os.environ.copy()
    environment["RELEASE_TAG"] = f"v{package_version}"
    environment["PACKAGE_VERSION"] = package_version
    environment["RELEASE_COMMIT"] = "dry-run-no-publication"
    environment["PRERELEASE"] = "true" if key[3] != 3 else "false"
    fake_cli = """
gh() {
  if [ "$1 $2" = 'release view' ]; then
    [ "$RELEASE_EXISTS" = true ]
    return
  fi
  printf 'dry-run gh'
  printf ' <%s>' "$@"
  printf '\\n'
}
"""
    for exists in ("false", "true"):
        environment["RELEASE_EXISTS"] = exists
        result = subprocess.run(
            [bash, "--noprofile", "--norc", "-c", fake_cli + publication_commands()],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Publication dry-run failed: {result.stderr}")
        print(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-version", required=True)
    arguments = parser.parse_args()
    validate_packages(arguments.package_version)
    dry_run(arguments.package_version)
    print("Real package validation and both publication paths passed (no GitHub writes).")


if __name__ == "__main__":
    main()
