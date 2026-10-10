# Development and releases

This guide is for contributors and maintainers. For prebuilt Windows
packages and first-time setup, see the [user-facing README](../README.md).
Run the commands below from the repository root.

## Run from source

Requirements: Python 3.13 and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
uv run rocket-lantern
```

PySide6 provides Qt and its native WebSocket client: no additional network
library is required. SQLite is included in Python. Resolved dependency
versions are recorded in `uv.lock`.

## Build Windows packages

Building requires Windows x64, `uv` and Inno Setup 6. The application
version comes from `pyproject.toml`, dependencies from `uv.lock`.
PyInstaller is a build-only dependency: it bundles Python and the Qt modules
used. Inno Setup produces the installer.

```powershell
.\scripts\build-windows.ps1
# If the compiler is not in its usual location:
.\scripts\build-windows.ps1 -IsccPath 'C:\tools\InnoSetup\ISCC.exe'
```

The script runs without interactive prompts and fails if any step fails.
Deliverables are in `dist/installers/`: an `.exe` installer and a portable
`.zip`. The standalone application is also in `dist/RocketLantern/`.
Keep this entire directory alongside its `.exe`.

The installer uses `%LOCALAPPDATA%\Programs\RocketLantern`, creates a Start
menu shortcut and offers a desktop shortcut. It runs without administrator
rights and includes an uninstaller. History and preferences stay in
`%LOCALAPPDATA%\RocketLantern\RocketLantern\matches.sqlite3`; updates and
uninstallation preserve them. The installer ID remains unchanged: an
existing installation may retain its old directory during an update.

Silent installation, without launching the application:

```powershell
.\RocketLantern-1.0.1-windows-x64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
```

The `.github/workflows/windows-build.yml` workflow runs tests and lint on
every push, pull request or manual run, without a branch filter.
Windows packaging and installer testing run for a stable
`vMAJOR.MINOR.PATCH` tag, after checks pass. For example, `v1.0.1` builds
packages; `v1.0.1-alpha.1`, `v1.0.1-beta.1` and `v1.0.1-rc.1` run checks
only when pushed as tags. Branch pushes that change to a preview version
also build and publish, as described below.
A manual run can also build and publish an existing stable tag through
the optional `release_tag` input, even when launched from `main`. Without
that input, its selected reference must itself be a stable tag to publish.
All checks and builds use the selected tag's code, not the latest branch.
The tag must match the version in `pyproject.toml`,
otherwise the build fails before packaging.

To build the current version, after committing changes and pushing the
commit:

```powershell
git tag v1.0.1
git push origin v1.0.1
```

The installed executable, installer and portable ZIP are built on a Windows
runner. The installer and ZIP can be downloaded from the run's artifacts
for 30 days. After installation tests pass, the workflow publishes a GitHub
release with the matching release notes, installer and portable ZIP.
Only the publication job gets repository write permission. No additional
secrets are required. Executables are unsigned; Windows may show
SmartScreen warnings.

## Release notes

### Automatic previews

A branch push publishes a preview when `pyproject.toml` changes from the
previous pushed revision to a version such as `1.1.0-beta.1`, `1.1.0rc1`
or `1.1.0-alpha.1`. Update `uv.lock` with `uv lock` in the same commit.
Unchanged versions, stable versions, pull requests and new branches alone
do not publish previews. With multiple commits in one push, the final
version is compared with the version before that push.

The workflow tests and builds that exact commit, automatically creates
its version tag, and publishes a GitHub **Pre-release** using the standard
text in `releases/prerelease.md`. Preview releases never become **Latest**.
Python-normalized versions are used in package filenames (for example,
`1.1.0-beta.1` produces `1.1.0b1`). Use a new preview number for each build.

### Stable releases

Release notes are stored in `releases/release-<version>.md`, without the
tag's `v` prefix. Each file is written in English and can be reused as the
GitHub release description. See [version 1.0.1](../releases/release-1.0.1.md).
Create the matching notes before tagging a new version; missing or empty
notes fail the checks before packaging. Rerunning publication updates the
same release and replaces its two packages rather than creating duplicates.

For a tag created before automatic publication was added, commit and push
the updated workflow, then open **Actions → Windows build → Run workflow**.
Select `main` and enter the existing tag (for example, `v1.0.0`) in
`release_tag`. This rebuilds and tests that tag, then publishes its release.
There is no need to move or recreate the tag. Rerunning an older workflow
execution alone does not pick up the updated workflow.

## Development checks

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests use synthetic events, an in-memory database and offscreen Qt.
No game or network access is required.

French and English translations use versioned Qt Linguist `.ts` catalogs
in `src/rocket_lantern/assets/translations/`. After editing them, regenerate
the `.qm` files used at runtime:

```powershell
uv run python scripts/compile-translations.py
```

The Windows build validates and compiles catalogs automatically. No extra
translation dependency is needed beyond PySide6.

## Data directory migration

Version 1.0.1 uses `RocketLantern` as both the Qt organization and application
name. On Windows, data lives in
`%LOCALAPPDATA%\RocketLantern\RocketLantern\matches.sqlite3`.
The historical source is `%LOCALAPPDATA%\RLWinLoss\RLWinLoss`.

Startup automatically runs migration before opening `MatchStore`:

1. Copy the legacy directory into a temporary staging directory beside the
   destination, verifying every copied file with SHA-256.
2. Validate SQLite integrity, foreign keys and application tables. Consolidate
   any committed WAL data with SQLite's backup API on the staged copy.
3. Confirm the original files have not changed, then atomically publish the
   new directory with a migration manifest.
4. Revalidate the new files and remove individually verified originals.
   Remove the manifest after cleanup completes.

If cleanup is interrupted, the next launch resumes it using the manifest.
Changed originals or a changed destination stop cleanup instead of deleting
data. Copy and validation failures leave the original data intact.
Close other running instances before upgrading; locked files can prevent
migration. The original application directory is removed when empty; an
empty parent organization directory may remain.

If a new database already exists without a migration manifest, it takes
precedence: the old database is neither overwritten nor merged or deleted.
A nonempty new directory without a database blocks migration rather than
overwriting unrelated files. Symbolic links are not migrated.
Migration tests use temporary directories only, never a real user database.

## Documentation screenshots

Regenerate the screenshots using the real Qt widgets and fictional data:

```powershell
uv run python scripts/export-screenshots.py
```

The script renders offscreen with a dark Qt palette, uses an in-memory
database and never connects to the game or opens personal history.
It writes the two versioned PNG files in `docs/images/` for the README and
user guide. The root `assets/` directory remains ignored.
