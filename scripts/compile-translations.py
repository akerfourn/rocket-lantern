"""Validate and compile the versioned Qt Linguist catalogs without network access."""

import subprocess
import sys
from pathlib import Path
from string import Formatter
from xml.etree import ElementTree

import PySide6

DIRECTORY = Path(__file__).resolve().parents[1] / "src/rocket_lantern/assets/translations"


def placeholders(value: str) -> set[tuple[str, str, str | None]]:
    """Translations must preserve every formatting field and its format."""
    return {
        (field, specification, conversion)
        for _, field, specification, conversion in Formatter().parse(value)
        if field is not None
    }


def main() -> None:
    """Fail on incomplete catalogs, then compile them using the installed Qt tool."""
    executable = "lrelease.exe" if sys.platform == "win32" else "lrelease"
    compiler = Path(PySide6.__file__).parent / executable
    catalogs = sorted(DIRECTORY.glob("*.ts"))
    if len(catalogs) != 2:
        raise ValueError("Both French and English catalogs are required")
    for catalog in catalogs:
        for message in ElementTree.parse(catalog).findall(".//message"):
            source = message.findtext("source", "")
            translation = message.find("translation")
            if translation is None or translation.get("type") in ("unfinished", "obsolete"):
                raise ValueError(f"{catalog.name}: incomplete translation for {source!r}")
            translated = translation.text or ""
            if translated == "" or placeholders(source) != placeholders(translated):
                raise ValueError(f"{catalog.name}: invalid translation for {source!r}")
        subprocess.run(
            [str(compiler), str(catalog), "-qm", str(catalog.with_suffix(".qm"))], check=True
        )


if __name__ == "__main__":
    main()
