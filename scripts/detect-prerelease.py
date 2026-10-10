"""Detect version changes on branch pushes without publishing anything."""

import os
import re
import subprocess
import tomllib
from pathlib import Path


def prerelease_tag(current: str, previous: str) -> str:
    """Return a release tag only for a changed alpha, beta or rc version."""
    number = r"(?:0|[1-9][0-9]*)"
    pattern = rf"{number}\.{number}\.{number}[-.]?(?:alpha|beta|a|b|rc)[-.]?[0-9]+"
    if current == previous or re.fullmatch(pattern, current) is None:
        return ""
    return f"v{current}"


def main() -> None:
    if os.environ["GITHUB_EVENT_NAME"] != "push":
        return
    if os.environ["GITHUB_REF_TYPE"] != "branch":
        return
    current = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    before = os.environ["PUSH_BEFORE"]
    if before == "0" * 40:
        # A new branch alone is not a version change.
        return
    previous_file = subprocess.run(
        ["git", "show", f"{before}:pyproject.toml"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    previous = tomllib.loads(previous_file.stdout)
    tag = prerelease_tag(current["project"]["version"], previous["project"]["version"])
    if tag == "":
        return
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"publish=true\nprerelease=true\ntag={tag}\n")


if __name__ == "__main__":
    main()
