# RocketLantern 1.8.0

Play configurable sound alerts for match events and filter recorded events
in the match details and 3D map.

## Sound alerts

- Add rules in **Settings → Sound alerts** for goals, assists, saves, epic
  saves, demolitions inflicted and demolitions received.
- Target yourself, your teammates, your whole team, opponents or everyone.
  Rules follow the tracked account independently of the history filter.
- Choose Windows system sounds or import MP3, WAV, FLAC, Ogg, M4A/AAC,
  Opus and WMA files, subject to decoder support for their encoding.
  Imported files are copied locally so moving the original is safe.
- Preview sounds, adjust volume and play up to 16 sounds simultaneously.
  Replay actions are ignored and repeated notifications are briefly
  filtered. Epic-save rules take priority over general save rules.
- Alerts are disabled by default. Choose **Private matches only** or
  **All matches**, or disable them while keeping your rules.

## Event filters and 3D map

- Filter recorded events by player, assister or target, and event family.
  Combine player filters with multiple selected families, or reset them
  together.
- Share the filters between the event list and 3D map. Filtering keeps the
  camera position and player colors, and preserves the selected event
  when it remains visible.
- Fix team attribution on the map for older events after a player changes
  teams, using the team recorded with the event.

## Scoreboard overlay

- Show the same encounter markers as the live table beside player names:
  teal for the current session, gray for earlier match history.
- Markers follow the displayed-player filter and update when the session
  changes. The placement preview also includes example markers.

## Updating and Windows packages

Databases from 1.7.0 and 1.8.0 previews keep schema 6; no database migration
is needed. Existing history, sessions, labels, favorites and preferences
are preserved. Imported audio files are stored in `sounds` beside the
database; include that folder when backing up your data.

- `RocketLantern-1.8.0-windows-x64-setup.exe`: per-user installer.
- `RocketLantern-1.8.0-windows-x64-portable.zip`: extract the entire archive
  and run `RocketLantern.exe` from the extracted folder.

No separate Python installation is needed.
