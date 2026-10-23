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

The `.github/workflows/windows-build.yml` workflow starts with a lightweight
Linux preflight, without installing the application's dependencies. It
identifies releases and validates the tag, declared version and nonempty
release notes before allocating a Windows runner.

Branch pushes run this preflight only when `pyproject.toml`, the workflow
or the preview detector changes. Without a new preview version, they stop
there. Ordinary code and documentation pushes do not trigger validation.
Stable `vMAJOR.MINOR.PATCH` tags trigger publication regardless of branch;
preview tags are ignored after preflight. Branch pushes that change to a
preview version also build and publish, as described below.

Pull requests affecting code, tests, packaging, scripts, dependencies or
workflows still run Windows checks without publishing. Documentation-only
PRs skip the workflow. A newer revision cancels obsolete checks on the
same PR, but release checks and publication jobs are not interrupted.
If branch protection requires the checks job, allow documentation-only
changes to merge without that workflow, or keep PR path filtering off.

Windows validation runs lint and formatting first, then compiles
translations and runs tests with `pytest -x`. The first failing test stops
the suite; the test report is still retained. Packaging, installer tests
and publication run only after a release's checks pass.
A manual run can also build and publish an existing stable tag through
the optional `release_tag` input, even when launched from `main`. Without
that input, it runs validation only unless its selected reference is a
stable tag.
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
Package filenames use the exact installed distribution metadata version.
This can retain `1.1.0-beta.1`, even if `uv.lock` stores `1.1.0b1`. The
Windows job passes its actual package version to publication; publication
never recalculates it. Use a new preview number for each build.

### Local pipeline validation

Run the Windows build, then exercise the actual installer and portable ZIP:

```powershell
.\scripts\build-windows.ps1
.\scripts\test-windows-packages.ps1 -PackageVersion '1.1.0-alpha.1'
```

The second script installs into a fresh directory under
`build/package-tests/`, launches the installed EXE with `--smoke-test`,
simulates metadata left by earlier releases, reinstalls over it, and checks
that the app reports the expected version and unrelated packages survive.
It then uninstalls the test application and smoke-tests the portable ZIP.
It selects the exact version, not the first package in a directory.
Logs and portable files remain in the ignored test directory for inspection.

The installer accepts `/PIPELINETEST=1` for these isolated tests: a separate
AppId, no uninstall registry entry and no shortcuts. Normal installations
keep the historical AppId. Neither smoke test opens user data or contacts
the game's API or GitHub. CI runs the same validation script.

Publication tests execute the workflow's actual Bash commands with a fake
GitHub CLI. An actual GitHub upload still requires a CI run and its token.

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

## Rocket League installation discovery

The settings dialog searches only after **Check configurations** is clicked.
Filesystem and registry reads run on a Qt worker; closing the dialog does
not trigger another scan. Results stay in memory until the application exits.

On Windows, Steam roots come from the current-user/machine registry (both
registry views) and standard program directories. Both known locations of
`libraryfolders.vdf` are read, including legacy and modern entries, followed
by `appmanifest_252950.acf` in each library. Epic locations come from `.item`
manifests, `LauncherInstalled.dat` and standard game folders. The search
does not recurse through drives or contact launcher services.

Candidates must contain `Binaries/Win64/RocketLeague.exe` and `TAGame/Config`.
Duplicate directories are merged. The UI prefers `TAStatsAPI.ini`, falls
back to `DefaultStatsAPI.ini`, and warns when neither exists. Inaccessible
or malformed sources produce partial-result warnings rather than discarding
other installations. **Open folder** opens that installation's configuration
directory.

The desired `packet_send_rate` is saved locally (default 10, range 1–120).
Checks read the rate separately for each installation: lower is a warning,
equal is a match, higher is informational. A missing key inherits from
`DefaultStatsAPI.ini` when the selected file is `TAStatsAPI.ini`, otherwise
the disabled default is zero. These are installation-file values, not a
measurement of the running game's effective rate; user overrides can differ.

Changing the desired rate only refreshes comparisons. An explicit per-row
**Apply** backs up the checked file, then atomically updates only
`PacketSendRate`. Existing comments, other keys, encoding and line endings
are preserved. Backups are not overwritten. Changed files or inherited
defaults require another check. Duplicate sections/keys and unreadable files
cannot be edited automatically. No automatic elevation or game restart occurs.

Tests supply isolated launcher metadata and fake folder openers. Automatic
discovery is currently Windows-only; parsing and filesystem tests are portable.

## Update detection

The Qt network client reads the official repository's GitHub releases API
without credentials. No game data is sent. Checks start only from the real
application entry point, never from previews or tests. The saved channel
defaults to stable and controls startup, ten-minute and manual checks.

Release selection compares supported alpha/beta/rc and stable versions
numerically, ignores drafts and never offers a downgrade. Paginated requests
have timeouts and size limits. Errors leave the application usable.

Only an installed, frozen Windows bundle can launch an installer. Downloads
require a GitHub SHA-256 digest, match the declared size, stream into a
`QSaveFile` in the application cache, and become executable only after
validation. Missing integrity metadata falls back to the release page.
The user must confirm before downloading or opening the browser. The
installer runs interactively in the existing installation directory.
Portable/source installations update manually. No extra dependency is used.

PyInstaller copies the distribution metadata so the packaged app knows its
version. Before copying files, the installer removes only
`{app}\_internal\rocket_lantern-*.dist-info`, preventing metadata from older
releases from overriding the installed version. Other packages and the
separate user data directory are untouched. The Windows package test covers
this cleanup by reinstalling over multiple stale distribution directories.
Tests simulate network replies, downloads and process launches;
they never access GitHub or modify a real installation.

## Event recording

Schema 6 extends `match_events` with `source_event`, `origin`,
`position_subject` and `details_json`. The latter holds selected scalar
measurements, never the incoming JSON payload. `match_event_players` links
each occurrence to all its participants and their roles, including
simultaneous ball hitters. Unresolved references retain name, team and
shortcut hints without guessing a permanent identity from the name.
Migration preserves existing event IDs, coordinates, results and labels.
Applications supporting schema 5 or earlier cannot open the upgraded
database; keep a compatible backup if a downgrade is needed.

All discrete live API notifications with a nonempty `MatchGuid` are
recorded, including clock changes, lifecycle notifications, ball hits and
boost pickups. Unknown event types retain their name, time and recognizable
top-level coordinates, but not arbitrary payload fields. Historical replay
playback is excluded. Goal-replay boundaries are recorded; replayed actions
are not. Recording does not require selecting a player or joining a team,
and never creates a W/L result by itself.

Each occurrence has a local reception timestamp and the latest received
match clock and overtime flag, overridden by those in the event itself
when present. Missing clocks remain null. Reception timestamps provide
ordering, not an exact subsecond game timestamp. `GoalTime` is kept
separately as the previous round's duration. Coordinates remain in their
original Unreal world frame: ball positions and boost pickup positions are
distinguished, and neither is treated as a car position.

`BallHit` retains both ball speeds and all hitters. Goals and crossbar hits
retain the last-touch player and resulting speed; crossbar hits also retain
impact force. Boost pickups retain the amount and pickup type. Repeated
notifications are separate occurrences even when their fields and clock
are identical. Goal notifications retain the existing duplicate protection.
The API provides no unique occurrence ID, so repeated delivery cannot in
general be distinguished from a legitimate identical action.

`UpdateState` is not stored as a tick series. Available boolean player
flags (`bHasCar`, `bOnGround`, `bOnWall`, `bBoosting`, `bPowersliding`,
`bDemolished`, `bSupersonic`) produce `PlayerState:<field>` records only
when first observed, changed or no longer available. `origin='state'`
distinguishes these observations from actual API events. The selected
details are `previous` and `value`; null means unknown, not false.
Disconnects, pauses, match endings, departures and goal replays close known
intervals. The first flag after a gap is a fresh observation. No aerial
state or unavailable position is inferred. Flags unavailable to the client
cannot be recorded; no additional game access is attempted.

Successful writes clear pending events from the collector. Only current
flags, goal duplicate keys and two recent match summaries remain cached;
the full event history lives in SQLite. Failed writes keep pending events
and their match summaries for retry, even after another match starts.
The persistence signature uses an event revision rather than
the whole timeline, avoiding repeated full-history insertion attempts.
Unchanged ticks do not trigger writes while a match is in progress.
`MatchStore.events()` and `event_participants()` expose the stored records
without a new map or analysis interface.

Tests use synthetic messages and temporary databases to cover positions,
multiple participants, rapid identical contacts, missing fields, replay
filtering, coverage gaps, migrations and transaction rollback. API field
definitions are documented in the
[official Stats API reference][stats-api].

[stats-api]: https://www.rocketleague.com/developer/stats-api

## Positioned-event map

The event list reads events and participant hints in two bulk queries.
The match sheet lazily creates its **3D map** tab when opened, also using
two bulk queries rather than one query per point.
Only finite XYZ triples are projected; a missing coordinate is never
replaced with zero. Opening the map, selecting events and moving the camera
do not write to SQLite or change stored coordinates or player links.

`event_deduplication` hides exact positioned API repeats within 100 ms in
both views. Its identity includes the match, event type, participants,
exact XYZ coordinates and received measurements, but not the row ID,
receipt timestamp or sampled game clock. Incomplete positions and derived
state transitions are left alone. The original rows and IDs stay in
SQLite; linked selections use the first visible occurrence. The live
opponent-post counter shares the same bounded time-window filter.

`event_map_data` builds immutable positioned records. Player colors are
deterministic within a match and keyed by database identity, not display
name. Unresolved team/shortcut/name hints may define a match-local visual
key, without creating a permanent link. Otherwise the point stays gray.
On simultaneous ball hits, the first recorded hitter supplies the color;
the list retains every available hitter name.
The legend groups actors by their recorded event team, falling back to
their match roster team when no event team was recorded. Unknown teams stay
neutral; neither names nor goal ownership are used to guess a team. A player
who changed teams can appear in both groups with the same event color.

`map_projection` provides an orthographic orbit camera and fit-to-data
bounds. Geometry is an indicative standard Soccar outline with goals and
ceiling, based on the [RLGym field constants][field-dimensions]. It is not
arena-specific geometry. Recorded outliers remain visible, without
scaling the coordinates to force them onto the standard field.

`EventMapCanvas` paints the projection using existing QtGui/QtWidgets
components, without OpenGL, Qt3D, a web view or an additional dependency.
Points are depth-sorted; picking uses projected distance and depth.
Selection draws a contrasting ring and a ground reference line. Only
interaction or ordinary widget invalidation triggers repainting; there
is no continuous render loop or new telemetry collection.

The map and both event tables share occurrence IDs. Signal blockers avoid
selection feedback loops; clock-format and language changes preserve the
selection and camera. The map is not constructed for other match tabs.
Tests cover identity hints, invalid coordinates, projection bounds,
mouse/keyboard interaction, read-only storage, lazy loading and translation.

The match dialog enables native resizing/maximization and has a fullscreen
action with an F11 shortcut. A fullscreen-only Escape shortcut takes
precedence over the canvas deselection key. Leaving fullscreen restores the
previous geometry and maximized state without rebuilding the map. Outside
fullscreen, Escape retains its ordinary canvas/dialog behavior.

`MapCamera.target` is an optional world-space rotation pivot. Without it,
the projection fits the full scene; an explicit target stays at the viewport
center through rotation, zoom and resizing. Panning unprojects screen-space
movement onto the camera plane, retaining a fixed world-space depth.
Presets target the field center, goal opening centers or a positioned event.
These controls never modify event coordinates or SQLite. Top view preserves
the target and zoom; reset restores the original fit-to-data overview.
Centering and view actions share a single left-aligned `QToolBar`, separated
into visual groups. Native actions preserve keyboard access and overflow
menus on narrow windows; the selection action remains disabled until a
positioned event is selected. Action texts and tooltips translate in place.

[field-dimensions]: https://rlgym.org/Cheatsheets/game_values/

## Match assessments and global shortcuts

Database schema 4 replaces schema 3's `match_evaluations` with `label_lists`,
`labels` and `match_labels`. The latter is keyed by `(match_id, list_id)`,
with a composite foreign key ensuring that the label belongs to its list.
The existing internal `match_details.id`, timestamps, results and session
membership are preserved by a transactional migration.

Schema 5 adds `label_lists.family`, defaulting existing categories to
`tag`. Supported families are `tag`, `flag` and `shield`; label symbols
remain independent of the family. Builds supporting schema 4 or earlier
cannot open the upgraded database.

The category editor is a separate two-pane dialog. It keeps a local draft
and writes all categories and labels in one transaction on Apply. Closing
with changes asks before saving or discarding. Shortcut combinations live
in this editor; global activation remains in Settings. Both windows suspend
global shortcuts while open. The editor detects external catalog changes
instead of silently overwriting them.

The default list ID is `smurfing`; its original four label IDs are unchanged.
User-defined IDs use `custom:<uuid>` independently of names, colors or order.
Catalog definitions validate names, colors and references; there is no fixed
SQL enumeration of label IDs. Disabling a definition never deletes choices.
The legacy `MatchStore.evaluation()` API addresses the default list; new
callers use `store.labels.choices()` and `choose()` for independent lists.
Missing default choices mean `not_evaluated`, not `no_suspicion`; missing
custom choices are unassigned. Votes can precede a result without creating
a session or W/L outcome. Older builds supporting schema 3 cannot open the
upgraded database; downgrading requires a compatible backup.

The current-match badge follows the selected player's identified live match,
then keeps that last match after destruction or disconnection. Replays,
missing identities and player-selection changes disable its target. Menus
capture their match GUID when opened: a subsequent match cannot redirect
the click. History buttons emit explicit GUIDs and refresh without resetting
filters. Labels, tooltips and menu actions support in-place localization.

Windows shortcuts use stdlib `ctypes` with typed `RegisterHotKey` and
`UnregisterHotKey` calls. Qt's `QAbstractNativeEventFilter` receives
`WM_HOTKEY`; there is no keyboard hook, polling, input simulation or game
process access. `MOD_NOREPEAT` prevents held keys from repeatedly voting.
All nonempty enabled bindings register or none do; partial failures release
already registered combinations. Closing the app or destroying the owner's Qt
object releases its registrations and native filter.

Global shortcuts default to enabled when no permission preference exists;
explicit saved choices are preserved. The General checkbox saves its state
immediately. The category editor saves label bindings in one SQLite
transaction, and catalog changes automatically update registrations. It
uses single-chord `QKeySequenceEdit` controls. The
bindings reference stable label IDs, never list order. Legacy positional
bindings are migrated onto their original native IDs. A blank binding is
valid; inactive definitions are excluded from registration. The
controller suspends registration while Settings is visible and restores
only saved bindings afterward. Unsupported platforms retain mouse editing.
No extra dependency is required.

Tests use mocked Windows registration calls, synthetic native messages,
temporary SQLite databases and offscreen widgets. They cover migration,
match transitions, late events, stale menus, conflicts, lifetime cleanup
and translation without contacting the game or capturing real input.

## Windows game detection

`GamePresenceMonitor` is shared by all overlays and the connection
controller. It checks foreground visibility every 500 ms and refreshes
Rocket League process IDs every two seconds. Process names are matched
case-insensitively against `RocketLeague.exe`, independently of Steam or
Epic installation paths. Only matching IDs are retained.

The native adapter uses a read-only process snapshot and checks the
foreground window's PID, visible style and minimized state. It does not
read gameplay memory, inject code, capture input or request elevation.
See Microsoft's [process snapshot documentation][process-snapshot] and
[foreground window documentation][foreground-window].

Foreground state gates HUD visibility; process presence gates connection
attempts. Losing focus must never stop match recording or overwrite saved
overlay activation. Placement previews remain usable without the game.
Native Z-order guards consume the shared detector's poll signal rather
than creating additional foreground/process checks.

A process scan error produces an unknown state, not an absent game. Existing
connections are preserved; explicit reconnect can attempt the API when
detection is unavailable. Foreground inspection errors hide the HUDs without
changing known process presence. Unsupported platforms and offscreen
rendering retain the ordinary connection behavior without native polling.

Tests inject a fake presence API and mock the socket boundary. Package
smoke tests also simulate focus changes, without inspecting real processes
or connecting to the game.

[process-snapshot]: https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot
[foreground-window]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getforegroundwindow

## Local account names

`LocalPlayerLog` reads complete login lines in bounded binary chunks. It
tries UTF-8 first, then the system's legacy encoding (`locale.getencoding`)
for Windows ANSI logs. The fallback encoding can be injected for tests.
Decoding occurs only after a complete line arrives, so a multibyte
character split between reads is not replaced prematurely.

Account matching always uses `PrimaryId`. Once the matching player appears
in the Stats API, its Unicode display name replaces the log-derived name
in the selector and saved preference. Unchanged names do not trigger
repeated writes; refreshing a name does not switch the tracked account or
the selected history player. Tests use fictional account IDs and names.

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
