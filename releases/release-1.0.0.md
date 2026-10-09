# RocketLantern 1.0.0

First stable release of RocketLantern: a Windows desktop companion for
capturing Rocket League's official Stats API data, tracking session results
and reviewing match statistics locally.

## Highlights

- Track wins, losses, W/L difference, win rate and unknown results for a
  selected player.
- Filter by current session, previous sessions or full history, and by
  latest game mode, a specific playlist or all game modes.
- Start sessions automatically after a one-hour gap between results, or
  manually without deleting history.
- Review session totals, per-match averages and detailed match sheets with
  participants, scores, goals and important events.
- Follow the current match's score, clock, overtime, player counters and
  ball information independently of history filters.
- Monitor teammates' boost with compact color-coded gauges and animated
  empty-boost alerts. Position the gauges on the left or right; the selected
  player's gauge stays gray.
- Switch between French and English instantly, including open detail
  windows, without reconnecting. Language and display preferences are saved.
- Keep results, structured match data and preferences in a local SQLite
  database, with automatic reconnection and duplicate-result protection.
- Inspect a bounded in-memory diagnostic journal with redacted identities.

## Windows packages

- `RocketLantern-1.0.0-windows-x64-setup.exe`: per-user installer with an
  uninstaller; administrator rights are not required.
- `RocketLantern-1.0.0-windows-x64-portable.zip`: portable application.
  Extract the entire archive and keep all files alongside the executable.

Both packages include Python and the required Qt components. No separate
Python installation is needed. Executables are unsigned, so Windows may
display a SmartScreen warning.

## Getting started

Close Rocket League and enable its Stats API in
`TAGame\Config\TAStatsAPI.ini`, or `DefaultStatsAPI.ini` if the former does
not exist. Update the existing section without duplicating it:

```ini
[TAGame.MatchStatsExporter_TA]
PacketSendRate=1
WebPort=49124
```

Restart the game, launch RocketLantern and select your player during a
match. The application connects only to the local game API. The local port
is configurable; RocketLantern does not modify game files.

See the [official Stats API documentation][stats-api] for configuration.

## Existing installations

Existing history and preferences are preserved. The database remains at
`%LOCALAPPDATA%\RLWinLoss\RLWinLoss\matches.sqlite3`, including after the
rename to RocketLantern. Updates and uninstallation do not delete it.
Older matches do not receive detailed statistics retroactively.

## Important limitations

- Tracking starts when the application receives events; past account
  history is not imported automatically.
- An interrupted match without a confirmed winner is recorded as unknown,
  not as a loss. A later confirmed result can replace it.
- Statistics may be partial, and events cover only the connection period.
  Missing values remain distinct from received zeros.
- Historical replays are excluded from tracking. Live boost and speed
  measurements stay in memory and are not stored as time series.
- Boost visibility depends on what the game sends. An omitted teammate
  boost field triggers an approximate-zero alert, not a confirmed value.
- Event coordinates are stored as reported by the API; their interpretation
  has not been validated against actual goal positions.

[stats-api]: https://www.rocketleague.com/developer/stats-api?lang=en
