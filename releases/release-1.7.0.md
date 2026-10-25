# RocketLantern 1.7.0

Explore recorded match events in 3D and display the live scoreboard in
its own overlay.

## Match events and 3D map

- Record more discrete events, including ball touches, crossbar hits and
  boost pickups, with timestamps, participant links and positions when
  available. Available player movement flags are stored as changes,
  without saving every tick or continuous trajectories.
- Open the **3D map** tab in match details to view positioned events on
  a schematic field. Points use player colors, with a team-grouped legend;
  selecting a point or list entry highlights the same event.
- Rotate, zoom and pan the map, or center it on the field, either goal or
  the selected event. Resize, maximize or use **F11** for fullscreen.
- Switch event times between minutes:seconds and seconds. Exact impact
  notifications repeated within 100 ms are filtered from event views
  without changing the stored records or coordinates.

## Live scoreboard and match summaries

- Use a more compact live header with the score, clock and status icons.
- Group players by team, show the tracked player's team first, sort each
  team by score and display team totals for every statistic.
- Read compact statistic icons instead of wide column labels. Saves show
  observed epic saves in parentheses; a separate counter tracks hits on
  the opponents' posts and crossbar, with repeated impacts filtered out.
- Recognize previously encountered players with badges that distinguish
  the current session from earlier history.
- Match and session summary cards now emphasize per-match averages, using
  the same statistic icons. Hover over a card for totals and data coverage.

## Scoreboard overlay

- Enable a separate scoreboard in **Settings → Overlay → Scoreboard**.
  Choose **All players**, **My team**, **Opposing team** or **My player
  only**. Team filters follow the tracked account, independently of the
  history selection.
- Save its activation, player filter, screen, placement and opacity
  independently of the W/L and boost overlays. Use the fictional preview
  to place it before joining a match.
- The overlay is disabled by default and includes no boost column. Use
  Rocket League's **Borderless** or **Windowed** mode for desktop overlays.

## Results and startup recovery

- Prevent a previous casual match's winner from confirming a new match
  before kickoff. The fallback winner state requires an observed live
  transition; the match-end event can still confirm the actual result.
- Automatically repair premature results and end times when saved
  kickoff, end and participant events provide sufficient evidence.
  Sessions, annotations and event records are preserved.
- Check for stable updates or previews directly from the startup error
  window, even when the database cannot open. Installed Windows builds
  can download and install after confirmation; portable and source builds
  open the release page instead.
- Explain incompatible database versions and reject newer schemas before
  any schema writes. Recovery checks do not access the database or change
  its saved update preferences.

## Updating and Windows packages

Close RocketLantern and back up its local data before updating. Upgrading
from 1.6.x migrates the database from schema 5 to schema 6 automatically,
preserving history, sessions, labels, favorites and preferences. Earlier
stable builds cannot open the migrated database; retain the backup if you
may need to downgrade. Existing 1.7.0 previews already using schema 6 keep
that schema. Older matches do not gain event or state data retroactively.

- `RocketLantern-1.7.0-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.7.0-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning.
