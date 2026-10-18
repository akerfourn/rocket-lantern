# Boost overlay: sources and RocketLantern's position

English | [Français](boost-overlay-fair-play.fr.md)

Sources checked on October 18, 2026.

RocketLantern offers a different way to display teammate boost. Our
position is that this is interface customization, not a tool designed
for cheating. These are the sources and technical choices behind that
position.

## Psyonix's interface design choice

In its [official announcement of April 15, 2024][announcement], Psyonix
introduced teammate boost gauges on nameplates. It explained choosing
nameplates over a permanent HUD through readability and distraction:

> would be difficult to follow and would distract from gameplay.

The article also describes the usefulness of this information for team
decisions. We read this choice as a readability trade-off: RocketLantern
offers a different display compromise, left to the user's preference.

## What our overlay does

The current implementation:

- receives messages from the game's built-in local Stats API;
- displays only the selected player's teammates, excluding that player
  and opponents;
- uses an external window, without injection, reading gameplay memory,
  automating gameplay actions or bypassing anti-cheat;
- does not reconstruct hidden boost from movement or pickups.

These details can be checked in the [API client][client],
[teammate filter][filter], [gauges][gauges] and [Windows placement][windows].
The latter identifies the foreground process and manages our window;
this does not read gameplay memory.

## Why we view this as display customization

The game already provides an indication of allied boost. RocketLantern
presents this team resource in a separate display suited to individual
preferences. Players remain responsible for their decisions and actions;
the overlay neither plays for them nor displays their opponents' boost.

Our position rests on this scope: offering a different presentation of
team information transmitted by the game without changing its mechanics
or bypassing its protections.

## Data filtered by the game

The behavior observed by project users distinguishes client roles:
spectators receive boost for both teams, while players receive their
teammates' boost, not their opponents'. This filtering is consistent with
access to information tailored to the client's role.

The [Stats API documentation][stats-api] itself describes several visibility
levels, including **TEAM** and **SPECTATOR**. The `Players.Boost` entry is
still marked **SPECTATOR**; an incomplete description of the player case
is one possible explanation for this difference, while the observed
behavior applies team-based filtering.

RocketLantern uses information actually transmitted by the game without
trying to obtain values it does not provide.

## Status and precautions

The [Rocket League Code of Conduct][conduct], under “Third-Party Mods”,
prohibits competitive advantages in online play.
[Section 4 of Epic's Terms of Service][terms] prohibits cheat tools and
their distribution, among other things.

Our position is not official permission from Epic/Psyonix. Without written
confirmation addressing this exact use, we retain an option disabled by
default and a warning about the risk of sanctions, accepted before first
activation. This note therefore does not guarantee protection from a ban
or replace the game's rules or a competition's requirements.

[announcement]: https://www.rocketleague.com/news/teammate-boost-indicators-and-rarity-name-changes-coming-to-rocket-league
[stats-api]: https://www.rocketleague.com/developer/stats-api?lang=en
[conduct]: https://www.rocketleague.com/code-of-conduct?lang=en
[terms]: https://legal.epicgames.com/epicgames/tos?lang=en-US
[client]: ../src/rocket_lantern/client.py
[filter]: ../src/rocket_lantern/boost_overlay.py
[gauges]: ../src/rocket_lantern/boost_gauge.py
[windows]: ../src/rocket_lantern/windows_overlay.py
