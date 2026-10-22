# Detailed user guide

[English](user-guide.md) | [Français](user-guide.fr.md)

For downloads, installation and initial game configuration, see the
[README](../README.md).

![RocketLantern match history and player statistics](images/rocket-lantern-matches.png)

Preview with fictional players and match data.

## Usage

On first launch, the setup guide offers to find your Steam and Epic Games
installations and configure their `PacketSendRate`. Searches and file
changes only start when you click their respective buttons. You can also
choose the language and local port; **Finish** reconnects the app if you
changed the port. You still need to check the game's `WebPort` manually.

Finishing, choosing **Skip for now**, or closing the guide is remembered,
so it does not appear automatically on the next launch. Reopen it from
**Settings → Rocket League → Setup guide** whenever needed. Existing users
with a selected
player or saved matches are not prompted automatically.

Detected paths are saved in the local database, but INI contents and
configuration validity are not cached. After a restart, remembered paths
are marked as requiring a check. Click **Check configurations** to reread
the files before applying a setting. There is no startup or periodic
installation scan. A partially inaccessible search preserves earlier
paths; a complete search replaces them.

1. Start the application, then a Rocket League match.
2. Your Steam or Epic account is detected automatically on Windows. If
   detection fails, select your player in the list; their ID is remembered.
3. Keep the application open until the match result arrives.

On Windows, the app waits for Rocket League before connecting. It connects
automatically when the game starts and stops connection attempts when it
closes. Detection can take about two seconds. Alt+Tab and minimization
do not disconnect the API or interrupt match recording.

Account detection reads primary login/logout events from
`Documents/My Games/Rocket League/TAGame/Logs/Launch.log`, using the Windows
Documents location even when redirected to OneDrive. It follows account
changes while the game runs. Missing or unreadable logs leave manual
selection available; no account password or authentication token is used.

When an account is detected, the **Player** list filters history only.
Recording, the live view and teammate boost overlay stay attached to the
connected account. Without automatic detection, manual selection controls
both history and the tracked player unless the game is detected as closed.

If game detection fails, an existing connection is kept. **Reconnect**
can still attempt the API connection when detection is unavailable.

Open **Settings** to choose **Français** or **English**. The preference
is saved locally. Labels, filters, tooltips and open detail windows update
immediately without restarting the application or reconnecting to the game.
Dates and decimal separators follow the selected language. Player names,
IDs, arena names and API data are not translated. Existing log entries keep
the language used when they were recorded.
On first launch, the system language selects French or English.

Settings are split into **General**, **Rocket League** and **Overlay**.
General contains connection, language, startup tab, updates, global shortcut
permission, favorite players and the label editor. Each section scrolls
independently on small screens; **Close** stays visible below the tabs.

Wins, losses, their difference, win rate and unknown results appear above
the tabs. A check and a cross distinguish outcomes without relying solely
on color. The summary and selectors remain visible in **Matches**,
**Live match** and **Logs**.

Selectors filter the summary, player statistics and the last 100 displayed
observations. Summary counts and averages cover all matches matching the filter,
including those beyond these 100 rows.
Defaults are the current session and latest game mode. The latest mode
automatically follows the playlist announced by the game; returning to a
mode restores its results within the session. **All game modes** combines
playlists. The period can also select an older session or the full history.
Selecting a session updates the overview without opening a window.
**Session details** opens the entire session across all playlists: averages
per match, dates, outcomes, arenas, scores, overtime and the selected
player's statistics for each match. Clicking a match opens its participants
and events. Detail windows show the data saved when they were opened.

The overview displays points, goals, assists, saves, shots, ball touches,
demolitions and car contacts, using the live table's icons. Each card
highlights the average with a small **/ match** suffix. Missing values
appear as “—”; averages exclude missing values, not received zeros.
Partial data and unknown results contribute to statistics. Hover over a
card for the number of matches with data; cumulative totals and sample
counts are not displayed on the cards.

A new session starts after a gap of at least one hour between results.
Every session has a database ID per player, independent of playlists.
**New session** immediately creates an empty session and resets its counters
without deleting history. The next unsaved result joins it, even if the
match is already in progress. A late correction stays in the match's
original session. Sessions, including empty ones, survive restarts.
After one hour without a result, or since an empty session was created,
the current session is empty until the next result creates a new session.
When first launching this version, older data is migrated automatically:
initial grouping using the one-hour rule, then permanent ID assignment.
These groups are no longer recalculated.

Unknown results are excluded from the win rate. Game modes appear live and
in history, such as `Ranked 2v2`, `Casual 3v3` and `Private match`. API IDs
remain visible; unlisted IDs are shown as unknown. Dates refer to when the
result was observed and are displayed in local time.

### Favorite players

Click the star next to **Player** to bookmark the selected account, or
remove it when the star is filled. Favorites appear first and stay
available while Rocket League is closed. Closing the game keeps the
history selection; browsing offline does not change the tracked account.

To find a previous teammate, opponent or another account, open
**Settings → General → Manage favorite players…**. Search by name or
identifier among players from saved matches, then click their star.
Changes are saved immediately. Old non-favorite players stay in this
window rather than cluttering the main selector.

Favorites provide access to data already stored on this computer. They
do not fetch online statistics or replace the detected account with a
friend for tracking. Live match data and boost gauges stay attached to
the detected account, independently of the history filter.

### W/L overlay

The pop-out button at the top right of the summary banner opens the W/L
overlay settings directly, without enabling the overlay.

In **Settings → Overlay → W/L summary**, enable **Show overlay** and choose the
game’s screen. Icons and numbers show wins, losses and their signed delta,
without W/L labels. They use the same player, period and game-mode filters
as the banner. Clicks pass through the overlay.

**Opacity** ranges from 10 to 100% and affects the entire overlay:
background, text and icons. The W/L and boost overlays save independent
values, also used in their placement previews. The default of 100% keeps
the existing appearance.

Under **Content**, select **Wins**, **Losses**, **Delta** and any annotation
categories you want to show. Each selected category displays the current
or last match's label icon, just like the application's summary banner.
It uses the configured icon family and color and follows manual edits
and shortcuts. A new match starts as “Not evaluated”. Disabled categories
are hidden. Choices are saved and applied immediately to the overlay and
its placement preview, without changing the summary filters. Only the
three counters are shown by default.

Choose a corner or click **Position overlay…**. An editor opens on the
selected screen: drag the summary, then **Save** or **Cancel**. Escape also
cancels. Only this preview accepts mouse input; the live overlay remains
click-through. Placement is saved locally, relative to the screen size,
and kept within the screen if the resolution changes. You can set it up
before enabling the overlay. A missing monitor temporarily falls back to
the primary screen without erasing the saved target.

The positioning panel becomes semi-transparent when the preview moves
behind it, then returns to normal opacity once clear. Its buttons remain
usable.

In the editor, the three **Horizontal anchor** icon buttons choose which
part stays fixed when the content gets wider: **Left**, **Center** or
**Right**. Hover over a button to see its name. Changing the
anchor does not move the preview. This setting is saved separately for
each overlay; the vertical position is unchanged. The overlay is still
kept within the screen edges.

**Locate**, next to **Reset**, briefly pulses a yellow marker around the
preview so you can find it. It works for both overlays without changing
their position or activation.

Use **Borderless** or **Windowed** display mode in Rocket League. Visibility
is not guaranteed in exclusive fullscreen. On Windows, both overlays appear
only while Rocket League is in the foreground. Alt+Tab, minimizing or
closing the game hides them without disabling their saved preferences.
Minimizing RocketLantern does not hide them if the game remains active.
The placement editor remains available without the game. Overlays close
with RocketLantern and are disabled by default.
Their activation preferences are restored at the next launch.

### Teammate boost overlay

**Settings → Overlay → Teammate boost** has a separate option showing only
named boost gauges for the detected account's teammates, or the manually
selected player when detection is unavailable. It excludes that player
and opponents. You can enable it independently of the W/L
summary, with its own screen and placement. Use **Borderless** or
**Windowed** mode here as well.

The **Display** setting offers three choices:

- **Never** (default).
- **Private matches only**: private matches, local/LAN matches, online
  free play, and offline or training modes.
- **All matches**: no game mode restriction.

Your choice is saved. Private-only mode excludes matchmaking, including
casual playlists, as well as tournaments. If the game mode is unknown,
the overlay stays hidden in this mode. An overlay enabled before this
setting was introduced keeps the **All matches** choice.

**Warning: risk of a ban.** [Epic's third-party tool rules][third-party-tools]
exclude competitive advantages in online play. Showing teammate boost
could fall into that category; RocketLantern guarantees neither permission
nor protection from sanctions. The option is disabled by default and
requires confirmation when first enabled. Activation and acceptance of the
warning are remembered, so neither needs to be repeated at each launch.

Our [fair-play note](boost-overlay-fair-play.md) sets out the sources,
our reasoning and the remaining uncertainties.

**Position overlay…** uses fictional gauges to let you arrange it outside
a match without enabling the actual HUD. Placement is saved separately
from the summary. During play, gauges use the same colors and animated
red zero-boost alert as the Live match tab. “≈ 0 %” marks an omitted field
treated as zero for the alert, not a confirmed value.

The overlay hides without an identifiable teammate, during goal replays,
at match end or on disconnect. It also hides after three seconds without
a new state to avoid showing stale boost. It reuses the existing connection
and latest state; no additional boost measurements are stored in SQLite.

[third-party-tools]: https://www.rocketleague.com/code-of-conduct?lang=en

### Manual match assessment

The icon-only tag just after the W/L delta is independent of the history
filters. It targets the **current match**, or the **last match** after it
ends. Click it to open the selector and choose:

- **Not evaluated**: no assessment, the default for every new match.
- **No suspicion**: you reviewed the match and did not suspect smurfing.
- **Possible smurf**: you suspect smurfing.
- **Strong suspicion**: your suspicion is strong, not an objective finding.

The tag changes its interior symbol (dash, check, question mark or
exclamation mark) as well as its color. Hovering shows the selected label
in a tooltip. Both labels and menus update when the language changes.

After a match ends or observation disconnects, its tag stays editable until
a new identified match is observed. A different match ID starts unreviewed;
reconnecting to the same match restores its saved assessment. Historical
replays and observations without a usable match/player identity cannot be
assessed using the current-match tag.

Use the compact tags at the right of **Matches** to edit an earlier match.
Each assessment belongs to the match, not a session, filter or player
selection. Editing an earlier match does not change the current-match tag.
Choices are saved locally in SQLite, including votes made before a result
arrives. They neither modify W/L outcomes nor send reports to Epic.

#### Categories and labels

Open **Settings → General → Manage labels**. A separate window shows
categories on the left and the selected category's labels on the right.
The supplied **Smurf suspicion** category can be renamed or disabled.
Each active category adds an icon-only button to the banner and history.
A match has at most one label per category; choosing one leaves the other
categories alone. **Not evaluated** clears a custom category's choice.

Choose the category's icon family: **Tag**, **Flag** or **Shield**. Each
label has its own name, inner symbol, color and optional shortcut. Select
a row to edit it below the table; its checkbox controls activation. Use
**Move up** and **Move down** to reorder categories and labels.

**Apply** saves the entire draft together. Switching categories keeps
unsaved edits; closing prompts you to save or discard them. Disabling a
category or label removes it from usable choices without erasing historical
annotations. There is no permanent deletion in this window.

Custom names stay as entered. Native names keep their translations until
renamed. Existing assessments are automatically preserved in the default
category. Existing categories retain the Tag icon family.

#### Optional keyboard shortcuts on Windows

Mouse editing is always available. Global keyboard shortcuts are enabled
on first launch. The **global keyboard shortcuts** checkbox in
**Settings → General** saves its state immediately. Existing explicit
preferences are preserved when updating.

Assign combinations in **Manage labels**, on each label's **Shortcut**
field, then click **Apply**. Leave a field empty for no shortcut; the eraser
icon clears a combination. Disabled categories and labels have no
registered shortcuts. The four bindings below are the initial values for
the default category. Saved changes are applied automatically; there is
no separate shortcut confirmation button. Registration resumes after
closing Settings and Manage labels.

| Default shortcut | Assessment |
| --- | --- |
| Ctrl+Shift+F1 | Not evaluated |
| Ctrl+Shift+F2 | No suspicion |
| Ctrl+Shift+F3 | Possible smurf |
| Ctrl+Shift+F4 | Strong suspicion |

Use one combination containing Ctrl, Alt or Shift with a letter, digit or
F1–F24, excluding F12 and Windows-key shortcuts. Combinations must differ.
If Windows cannot register one, no assessment shortcut remains active;
open Settings to see the error and choose other combinations.

Registered shortcuts work without focusing RocketLantern. They affect the
current or last observed match, never a selected row in history. No usable
target means no change. Holding a key does not repeat the vote.
Shortcuts are suspended while Settings or Manage labels is open, so
recording a new binding does not annotate a match. Unsaved edits are
ignored; the previously saved
configuration resumes when the window closes. Closing RocketLantern
releases its registered shortcuts.

RocketLantern registers only these combinations through Windows; it does
not record other keyboard input, inject into the game, or simulate keys.
This design does not constitute an anti-cheat compatibility guarantee.
The settings window scrolls on smaller screens while keeping **Close**
visible.

### Live match

The score and clock are centered in a compact header above the player
table. The tracked player's team score is underlined. Hover over the icon
on the left for the match phase, game mode and arena. The eye is blue or
orange for the tracked team and neutral for an overview; a clock marks
waiting for match data. A neutral eye means no tracked team is identified.
History filters do not affect this view. The table's tooltip explains
missing values and the bold tracked player.
Overtime adds a **+** prefix to the clock.

Statistic headers use icons: a podium for points, a ball with impact lines
for shots, and a plain ball for touches. Hover over a header to see the
statistic's full name.

A small marker beside a player's name identifies a previous encounter:
teal in the tracked account's current session, gray in other saved
matches across all accounts and game modes. The current session takes
priority, and the tooltip identifies the context. Recognition uses player
IDs, not display names; the tracked player and the displayed match are
excluded. History filters do not affect these markers.

The saves column shows **3 (1)** for three saves including one epic save,
for both players and team totals. Parentheses appear only when an epic
save was observed. These counts come from received `EpicSave` events;
joining a match late or reconnecting can miss earlier epic saves.

The goal frame icon counts observed `CrossbarHit` events on the opponent's
posts or crossbar, credited to the last player who touched the ball. The
impact position and that player's team determine the side. Hits on their
own goal frame, replays and events without identifiable sides or players
are excluded. Each team row totals its present players' counts. Like epic
saves, only events received while following the match can be counted.

A gauge shows the selected player's boost, and a named gauge appears for
each present teammate, identified by ID and team. With automatic detection,
history selection does not change this team. Otherwise, manual player
selection changes it. Gauges form a compact 240-pixel column
with names above the bars. **Boosts: Left / Right** is saved locally.
At a tab width of 900 pixels or more, the column sits beside the table;
otherwise, it remains above the table, aligned to the chosen side.
The table separates teams into tinted blocks with blue/orange markers
beside player names. The tracked team comes first, and players in each
team are ordered by descending points. Each team's heading row sums every
statistic for present players. **≥** marks a partial total when some
counters are missing; its tooltip shows how many were received. A total
with no received values stays **—**. Boost appears only in the gauges.
The score above retains its blue/orange dots and underlines the tracked
team's score.

Teammate gauges are green above 50 %, orange above 25 %, and red at or
below 25 %. At 0 %, the entire red bar shows animated loading-style stripes
with “0 % · empty” beside it. The selected player's boost stays gray,
without a zero-boost alert animation. Animations stop when the view is
hidden. If a present teammate's `Boost` field is omitted, their gauge shows
the same animated red alert as zero, with “≈ 0 %”: this is a display
assumption, not a received value. An invalid value or a player explicitly
without a car remains a disabled “—” gauge. This assumption is not applied
to the selected player. Values and colors update with each received state
without recreating gauges for every packet.

The table also shows received values for other players. The display does
not assume that only the local player is visible. Missing or invalid fields
remain “—” in the table and received state, not zero. An omitted value is
not carried over from an older state; the “≈ 0 %” alert applies only to
teammate gauges. Visibility depends on data emitted by the game.
Boost is not inferred from pickup events.

The view retains only the latest state in memory: no boost or speed time
series is stored in SQLite. Events and movement-state changes are recorded
separately, as described below. Disconnecting or leaving the match clears
the live values. Goal replays retain the last non-replay data, with a note
in the status tooltip; historical replays are excluded from this live view.

We recommend `PacketSendRate=10` for ten periodic updates per second and
smoother live gauges. With `1`, updates arrive once per second.
Editing the INI requires restarting
the game. See the [official configuration][stats-api]. RocketLantern changes
only `PacketSendRate` when you explicitly click **Apply** for an installation
in **Settings**. **Check configurations** reads every detected installation
and compares its rate with your saved desired rate: lower is a warning,
higher is informational. Changes preserve other keys and save a backup beside
the file. The game must be restarted after changes.

Preferences and results are stored in `matches.sqlite3` in Qt's local
RocketLantern data directory. On Windows:
`%LOCALAPPDATA%\RocketLantern\RocketLantern\matches.sqlite3`.
Version 1.0.1 automatically migrates earlier installations at startup,
preserving history and preferences. Original files are removed only after
the copied data has been validated. No manual migration is needed.
Participant names and IDs are stored locally with their match statistics.
No remote service or additional account is used.

### Match details

Click a history row to open the match sheet: blue/orange score, followed
by **Players**, **Events**, **3D map** and **Information** tabs (arena, overtime,
playlist, last observation and IDs).
The table shows all observed players grouped by team. The selected player
is identified by ID, with a highlighted row and a “selected” annotation;
their team's score remains bold and underlined. The Events tab lists the
recorded match events, including goals, statistics events (`StatfeedEvent`),
ball touches, crossbar hits and boost pickups when the game sends them.
Use **Clock format** above the events to switch between minutes:seconds
and seconds. Minutes:seconds is the default, and your choice is remembered.
The **3D map** tab shows events with recorded XYZ coordinates beside a
linked list. The match window can be resized or maximized. **Fullscreen**
or **F11** fills the screen; **F11** or **Esc** returns to the previous
window size, without losing the camera position or event selection.

Centering and view controls share one action bar, with a separator between
the two groups.
Left-drag the map to rotate and use the mouse wheel to zoom. Right-drag,
middle-drag or **Shift + left-drag** moves the center of rotation. The
**Center on** buttons target the field center, either goal or the selected
event without changing angle or zoom. **Top view** keeps that target;
**Reset view** restores the initial overview, center and zoom.
Selecting a point or a row highlights the same event in both lists.
The legend below the map groups players by team with blue or orange
markers, keeping each player's individual event color. Missing teams stay
in a neutral group; an unknown author appears gray.
Goals use diamonds and boost pickups use squares. The selected point has
a white ring and a line to the ground to help read its height.

The arena is a schematic standard field, not an exact model of every map
or mutator. Points keep their recorded coordinates, including positions
outside that outline. These are ball or boost pickup positions, not car
trajectories. Events without three valid coordinates stay in **Events**
but do not appear on the map. The map uses the same clock format setting.

Each player retains their last received counters: points, goals, shots,
assists, saves, ball touches, car contacts and demolitions. Leaving the
match does not remove their statistics.

Goals retain the scorer, optional assister, team, ball speed and position
when available. Speeds are in Unreal units/s. The clock is the last value
received from the game; `GoalTime` remains separate and represents the
previous round's duration, not the goal's timestamp.
Event identities are linked to participants only when the ID or the
shortcut/team/name combination permits consistent attribution. An
unresolved identity remains missing, never assigned by name alone.

A missing value appears as “—”, distinct from zero. Without a state
received after the winner announcement, the score and statistics remain
the last observed values, potentially partial. Late states enrich an
already saved result without counting the match again. Even with a final
state, events cover only the connection period; departed participants
retain their last observed values. Replayed actions do not add statistics
or events; goal-replay start/end notifications remain in the timeline.

SQLite stores structured tables with internal IDs, foreign keys and
uniqueness constraints. No raw JSON message or continuous trajectory is
retained. Discrete events keep their reception time, available match clock
and coordinates. Positions describe the ball or a boost pickup, not a
continuous player trajectory. Available movement flags are recorded only
when observed, changed or lost; missing values remain unknown. These
records prepare future analysis and do not identify smurfs automatically.
Repeated touches remain separate, even within the same clock second;
duplicate goal notifications are filtered. Migration is automatic and
preserves existing history at the same location. Older matches do not
receive statistics retroactively. The updated database cannot be opened
by older builds supporting only schema 5 or earlier.

## Diagnostics: Logs tab

### Startup errors

If the app cannot start, its error window identifies the failing step:
application files, data folder, migration, database, translations or launch.
The diagnostic includes the version, exact exception, relevant path and
traceback. **Copy diagnostic** copies it without closing the window.
Nothing is uploaded automatically. Paths can include your Windows account
name; review the diagnostic before posting it publicly.

A missing database is normal on first launch: the app creates it. Do not
delete an existing database to resolve an error. For a portable version,
extract the entire archive and keep its files together. If antivirus
software is analyzing the app, wait for its verdict before trying again;
there is no need to disable protection to read the diagnostic.

### Connection and event logs

Restart the application after a code update, then open **Logs**.
The tab keeps the last 300 timestamped entries:

- WebSocket address, connection, disconnection and exact socket errors.
- Major match events, such as match start, goals and match end, without
  their JSON payloads.
- Invalid JSON messages and match-tracking rejection reasons.
- Saved results, message count and last receive time.

Repeated live updates, clock ticks and stat awards are not logged by
default. Every message still reaches tracking, live views and the receive
counter. Enable **API details** to capture all events and their redacted
JSON contents when troubleshooting. This option is off at each launch and
only affects subsequent messages, including while the Logs tab is hidden.

Logs remain in memory, with no automatic file saving. Names and IDs in
detailed payloads are redacted without altering tracking data. Entries
exceeding 2,000 characters are truncated with an explicit marker. Buttons
copy or clear logs, or pause scrolling. Pausing scrolling does not stop
collection; disabling API details does not erase existing entries.

The API may send `Data` as a JSON object or as a string containing JSON.
Both formats are decoded before tracking. Detailed logs show normalized
content. An invalid encoded `Data` field is fully redacted in detailed
logs; normal logs omit the payload and report the rejection reason.

**Connected does not mean events are arriving.** After ten seconds without
a message, the application shows a warning; this may be normal in menus.
Check reception during a match. With `PacketSendRate=10`, `UpdateState`
events are expected ten times per second while the game is sending data;
other events arrive in addition to these.

If the counter stays at zero during a match:

1. Check `WebPort=49124` and the same port in the application window.
2. Check `[TAGame.MatchStatsExporter_TA]` settings and fully restart
   Rocket League after changing them.
3. Also check the user file, if present:
   `Documents\My Games\Rocket League\TAGame\Config\TAStatsAPI.ini`.
   A value in `DefaultStatsAPI.ini` alone does not describe the user
   configuration. Automatic rate changes affect only the explicitly selected
   installation file, not this user override.
4. Copy connection and event/rejection entries from **Logs**.

Connection and reception are separate from counting: an event without
`MatchGuid` remains visible and its game mode is displayed, but no result
is saved without a reliable match ID.

## Limitations

- Tracking starts when the application receives matches; this API does not
  automatically import past account history.
- Leaving a match, closing the app or losing connection before the result
  produces an unknown result, without inferring a loss.
- A confirmed result received after reconnection replaces an unknown result.
- Loaded replays are excluded using `ReplayCreated`. At connection time,
  `bReplay=true` together with `Frame` / `Elapsed` also triggers exclusion.
  These fields alone are insufficient when `bReplay=false`. Goal replays
  during an already tracked match are not excluded. Connecting for the
  first time during a goal replay with these fields may be ambiguous:
  consult the logs.
- Only matches with `MatchGuid` and a known team for the selected player
  can be counted. Training is not counted.
- Win/loss uses the player's last observed playing team in that match
  before its result is confirmed. Moving to spectator does not erase that
  assignment; a match watched entirely as a spectator is not counted.
- Changing the tracked account interrupts current tracking. The new
  account is recognized at the next game update. History selection does
  not interrupt tracking when the connected account is detected.
- An abrupt process termination cannot save the active match.

[stats-api]: https://www.rocketleague.com/developer/stats-api?lang=en

Playlist names use a local ID table from this
[community reference][playlist-ids]. No BakkesMod installation is required;
all data comes from the official Stats API.

[playlist-ids]: https://bakkesplugins.com/wiki/bakkesmod-sdk/code-snippets/playlist-id
