# RocketLantern

<p align="center">
  <img src="src/rocket_lantern/assets/rocket-lantern-256.png"
       alt="RocketLantern logo" width="128" height="128">
</p>

Track your Rocket League wins and losses by session and game mode, review
match statistics, and keep an eye on your teammates' boost in real time.
A Windows desktop application with French and English interfaces.

## Download and install

**[Download the latest Windows release][latest-release]**

No Python, uv or developer tools are needed.

1. Open the release page and expand **Assets**.
2. Download `RocketLantern-<version>-windows-x64-setup.exe`.
3. Run the installer, then launch **RocketLantern** from the Start menu.
4. Enable Rocket League's Stats API using the instructions below.

The installer is for Windows x64 and does not require administrator rights.
It includes an uninstaller and offers a desktop shortcut. Executables are
currently unsigned, so Windows may display a SmartScreen warning.

Prefer not to install? Download
`RocketLantern-<version>-windows-x64-portable.zip`, extract the **entire**
archive, then run `RocketLantern.exe` from the extracted folder.
Keep all extracted files together.

![RocketLantern showing live scores and teammate boost](docs/images/rocket-lantern.png)

Preview with fictional players and match data.

## Enable Rocket League's Stats API

This one-time setup lets RocketLantern receive data directly from the game.

1. Close Rocket League.
2. In RocketLantern, open **Settings** and click **Detect installations**.
   Choose the installation if several Steam/Epic copies are found, then
   click **Open folder** to open `TAGame\Config`. Open `TAStatsAPI.ini`, or
   `DefaultStatsAPI.ini` if the first file does not exist.
3. Update the keys in the existing section below without duplicating it:

```ini
[TAGame.MatchStatsExporter_TA]
PacketSendRate=10
WebPort=49124
```

4. Save the file and restart Rocket League.

RocketLantern connects to `127.0.0.1` on port `49124` by default. If you use
a different `WebPort`, open **Settings**, set the same **Local port** and click
**Reconnect**. The TCP `Port`, if enabled, must differ from `WebPort`.

**Settings** also lets you change the language instantly and choose whether
**Matches** or **Live match** opens at startup. Preferences are saved locally.

### Updates

In **Settings**, choose **Disabled**, **Stable updates** (default), or
**All updates (unstable)**. Development versions may contain bugs.
RocketLantern checks GitHub releases at startup and every ten minutes.
Use **Check now** to check manually. Disabled means no update requests.

When a newer version is available, a download icon appears beside the app
name: green for stable, orange for a preview. Clicking it asks for
confirmation before any download. Installed Windows versions download and
verify the installer, then close RocketLantern and open the installation
wizard. Your local data is retained. Portable and source versions open the
release page for a manual update instead.

The recommended `PacketSendRate=10` provides ten periodic updates per second
for smoother live boost gauges. Restart the game after configuration changes.
RocketLantern does not modify game files.
Installation detection runs only when requested, using local Steam/Epic
metadata and known locations, without scanning entire drives. Unregistered
or moved copies may require locating the game folder manually.

See the [official Stats API documentation][stats-api] for more details.

## First match

1. Open RocketLantern and start a Rocket League match.
2. Select your player in the **Player** list. Your selection is remembered.
3. Keep the application open until the match result arrives.

Choose **Français** or **English** in the top-right corner. The interface
changes immediately without restarting or reconnecting.

### Sessions and results

Wins, losses, W/L difference and win rate stay visible above the tabs.
By default, the summary shows the **current session** and **latest game
mode**. Use the selectors to switch to another mode, all modes, a previous
session or the full history.

A new session starts automatically after a gap of at least one hour between
results. **New session** starts one immediately without deleting history.
Returning to a game mode restores its results within the selected session.

### Match statistics

The **Matches** tab shows history and the selected player's totals and
per-match averages: points, goals, assists, saves, shots, demolitions, ball
touches and car contacts. Click a match to see its players and events, or
use **Session details** to review a complete session.

Missing values appear as “—”, not zero. Statistics may be partial if the
application did not observe the whole match.

### Live match and teammates' boost

The **Live match** tab shows the score, clock and current player counters.
Your team's score is underlined.

Teammate boost gauges are green above 50 %, orange above 25 %, and red at
or below 25 %. Empty boost triggers an animated red alert. The selected
player's own gauge stays gray. Choose **Boosts: Left / Right** to position
the gauges for your screen setup.

“≈ 0 %” means a teammate's boost field was omitted: the alert assumes empty
boost, but this is not a confirmed value. Visibility depends on the game.
Live boost and speed measurements are not saved as time series.

## Local data and privacy

Update checks contact GitHub only; they do not send player or match data.
Disable update detection in **Settings** to stop those requests.

History and preferences are saved locally in:

```text
%LOCALAPPDATA%\RocketLantern\RocketLantern\matches.sqlite3
```

Starting with version 1.0.1, previous installations are migrated
automatically when the application starts. History and preferences are
preserved; the original files are removed only after a verified copy.
Updates and uninstallation do not delete this database.
Player names and IDs are stored with match statistics. No additional
account or remote service is used.

## Troubleshooting

**Connected, but no matches or events?**

- Check reception during a match: silence in the game menus can be normal.
- Check that the game's `WebPort` matches RocketLantern's **Local port**.
- Fully restart Rocket League after editing its configuration.
- If present, also check the user configuration at
  `Documents\My Games\Rocket League\TAGame\Config\TAStatsAPI.ini`.
- Open **Logs** for connection errors and received events. Logs stay in
  memory; player names and IDs are redacted.

Past account history is not imported. Leaving a match or losing connection
before a confirmed result records an **unknown**, not a loss. Unknown
results are excluded from the win rate. Historical replays are not counted.

See the [detailed user guide](docs/user-guide.md) for statistics, event data,
session behavior and additional diagnostics.

## More information

- [Releases and downloads][releases]
- [Development, Windows builds and release publishing](docs/development.md)

[latest-release]: https://github.com/akerfourn/rocket-lantern/releases/latest
[releases]: https://github.com/akerfourn/rocket-lantern/releases
[stats-api]: https://www.rocketleague.com/developer/stats-api?lang=en
