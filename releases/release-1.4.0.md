# RocketLantern 1.4.0

Keep your session results and teammate boost in view while playing, with
two independently positioned desktop overlays.

## W/L overlay

- Show wins, losses and their signed difference in a compact banner with
  icons, using the same player, period and game-mode filters as the app.
- Choose a screen and corner, or drag a preview to the desired position.
  Save the placement or cancel without changing it.
- Keep the overlay visible when RocketLantern is minimized, without
  intercepting mouse input or taking focus from the game.

Use **Borderless** display mode in Rocket League. External overlays are
not guaranteed to appear in exclusive fullscreen. No Game Bar component
or game injection is needed.

## Optional teammate boost overlay

- Display named boost gauges for the selected player's teammates only,
  excluding the selected player and opponents.
- Enable it separately from the W/L overlay, with its own screen and
  saved placement. A fictional preview lets you arrange it outside a match.
- Use green above 50 %, orange above 25 % and red at or below 25 %, with
  an animated red alert at zero. An omitted boost field is marked “≈ 0 %”,
  not presented as a confirmed value.
- Hide the gauges during goal replays, at match end, on disconnect or
  after three seconds without a new state, so stale boost stays off screen.

The boost overlay is disabled at each launch and requires confirmation
of a warning about the risk of sanctions, including a ban. RocketLantern
does not guarantee that this use is permitted by Epic/Psyonix or safe
from sanctions. Read the warning before enabling it.

Both overlays reuse existing match data. No additional boost telemetry
is saved to the database. Their positions are remembered, but activation
is not carried over to the next launch.

## Settings

Settings are grouped into **General**, **Rocket League**, **Overlay** and
**Shortcuts**, with separate controls for each overlay. Advanced placement
diagnostics remain available for troubleshooting. French and English
labels and user guides cover the new controls and Borderless mode.

## Updating and Windows packages

Close RocketLantern before installing. Existing history, statistics,
assessments and preferences are preserved; the database schema is unchanged.

- `RocketLantern-1.4.0-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.4.0-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed. Executables remain unsigned;
Windows may display a SmartScreen warning.
