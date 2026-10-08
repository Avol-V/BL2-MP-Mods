# Changelog

## 1.5.0 — October 8, 2026

Up to four players the game is balanced as without the mod; above four, enemies get tougher per player and, optionally, more numerous. The network settings of the original patch apply only above four players and are no longer saved to the game's ini files. No hotfixes are registered any more. Tested alone and with two players; more than four players were simulated by a probe that made the mod count five, six or eight players.

- **EffectiveNumPlayers follows the player count, up to four.** The game's balance reads EffectiveNumPlayers, which the original patch held at 4, so every session was balanced for four players, alone too. By the game's scripts, the solo Fight For Your Life time and the AI reset after a solo death also depend on it. The mod now sets it to min(players, 4) right after the game sets it, in POST hooks of PostLogin, Logout and HandleSeamlessTravelPlayer, and checks it on every pass. Above four, tables with "== 4" branches keep working; player vehicles no longer drop to minimum health. Checked alone (1) and with two players: 2 at once on join, 1 at once on leave.
- **The original patch's hotfixes are no longer applied.** With the game's own tables they are not needed, and the health one was wrong: it copied the damage table into the health table, so with four players and more normal enemies had 70% of their stock health and champions 33%. Experience shares and kill skill durations are now the stock values (1.0 / 0.9 / 0.85 / 0.8 experience, 0 / 0.04 / 0.05 / 0.06 killer bonus, kill skills 7 / 8 / 9 / 10 s for 1 to 4 players; the four-player row repeats up to 64), written directly to GD_Globals. The original patch set 0.8 / 0.06 and 1 s for every player count. In game a kill skill lasted 7 s alone and 10 s when the mod counted four players: the game picks the row by EffectiveNumPlayers. Hotfix registration is removed, and with it the pending registration without SHiFT.
- **New option Stronger enemies above four players, on by default, and Strength per extra player (0–200%, default 100%).** Above four players, every extra player adds the game's own step from three to four players to enemy health, damage, gun damage, shields, enemy vehicle health and the weights of badass and boss variants in population mixes (also the DLC witch doctor and wedding badass weights). For example, normal enemies' health in the first playthrough: 1.75 for four, 2.05 / 2.35 / 2.95 for five / six / eight players. The shield table tests "== 6" where four players were meant, so four players get 1.0; above four it continues from 1.0 by the intended step: 1.3 / 1.6 / 2.2. Enemy numbers are unchanged.
- **New option More enemies above four players, off by default.** Enemy dens add enemies by the game's step from three to four players (e.g. the most common formula: 2 extra enemies for four players, 3 / 4 for five / six); linear formulas such as one extra enemy per extra player keep growing past four; Constructors, necromancers and fire mages summon more, and the Son of Crawmerax fight spawns more. Missions that wait for every enemy may take longer; turn the option off if one gets stuck.
- The tables are changed by the mod's passes and apply to enemies that spawn afterwards; tables that load with a map are changed in the passes after it loads. Up to four players nothing is changed. Values were checked in game with a probe at five, six and eight counted players, after fast travel and back, and restored at one and two players.
- **New option Instant fast travel, off by default** (the original patch always set the 5-second countdown to 0).
- **The network settings apply only above four players**: tick rate, client rates, PRI update frequency, bandwidth and timeouts as in the original patch above four, stock values up to four. AdjustedNetSpeed is no longer set (the game recomputes it on every join and leave). With two players and the mod counting five, the switch reached the live net drivers and existing players' PRIs in both directions without disconnects; the connected client noticed no stutter. A connected client's net speed is not changed by the switch: the game only resets it when its computed per-player rate changes, which stays 7000.
- **No more ini changes.** Up to 1.4.0 the mod applied its settings with the console command set, which also saves config properties to the user's WillowEngine.ini and WillowGame.ini, as running the original cooppatch.txt does. The network values stayed there and the game used them without the mod. 1.5.0 writes values in memory only. Values in memory that equal the patch's network values before the mod writes them are taken for such traces and replaced by the stock values up to four players; see the README to restore the ini files for the game without the mod.
- Values are written only where they differ, so a pass after a map change no longer re-applies unchanged objects.
- Runtime diagnostics show player counts, the network block, the options, the experience and kill skill rows and every changed table; the hotfix status is gone.

Unchanged cooppatch.txt SHA256:
804f7f740ee2c1d0c5ca6a1e9dec5cbce4c9a6d3c7cf09407ff1c3b56b9712da

## 1.4.0 — October 8, 2026

Keeps squads when a game is loaded from the main menu, adds two optional vehicle tweaks from NoCap and fixes the packed archive name. Patch data and hotfix registration are unchanged. Tested alone and with two players; more than two players, including real squads, are untested.

- Squad teams (2, 3, …) are now created in the new GameInfo when a game is loaded from the main menu, as NoCap does in InitializeTeams. The game then moves each squad into its new team itself, at once and with correct team sizes. Fast travel, including to DLC maps, keeps the GameInfo and its teams (maps stream into the persistent Loader world), so squads already survived it. Checked with a probe that planned both players into team 2: the host was moved by the game at once; a client still loading was moved by the mod's next pass 0.1 s later; the ally panel showed on both screens.
- New option **Stand on vehicles**, off by default: players can stand on top of every vehicle, not only on the Sand Skiff and Fan Boat. Player vehicles load their chassis definitions with the vehicle, so the option is applied when each vehicle spawns. The host stood on the Runner and Technical; a client without the mod stayed on a Technical driven fast, with slight jitter.
- New option **Any vehicle at any station**, off by default: Catch-A-Ride stations offer every vehicle family. At a main-game station the host saw the Sand Skiff and Fan Boat next to the Runner and Technical and spawned a Fan Boat; a client without the mod sees the stock list. Unlock requirements and previews are unchanged (NoCap removes the Technical's mission requirement and replaces the Sand Skiff preview). Station definitions are updated after every map change, because DLC stations load with DLC maps. DLC stations are untested: the test character had not unlocked them.
- Turning a vehicle option off restores the stock values. Vehicle definitions are scanned only while an option is on, in the passes after a map change, one class per frame. The vehicle options also work for a client who installs the mod; nothing else runs on a client.
- The archive is now SDKMod/dist/unlimited_coop.sdkmod. The SDK imports a .sdkmod only if its single root folder has the archive's name, so the earlier unlimited_coop-<version>.sdkmod was ignored. The version stays in pyproject.toml and the build manifest. The archive alone loaded and ran in the game.
- The vehicle options are adapted from NoCap 0.2.2, © 2024–2025 stealmyhousekey, GPL-3.0.

## 1.3.0 — October 8, 2026, no separate release

Restores the HUD ally panel. Patch data and hotfix registration are unchanged. Tested with two players: the ally panel appears for both on join and survives travel, option switches, and a rejoin. More than two players, including squads, are untested.

- The panel shows only teammates. Up to 1.2.0 the PickTeam hook returned the requested team number, 255 (no team) in practice: the host stayed alone in team 0 (they join before the mod's hooks) and clients had no team, so no player saw anyone in the panel.
- Up to four players now share team 0, as in the unmodified game. The panel caches three allies and the game writes past them without a bounds check, so five players in one team would corrupt memory on every machine, including clients without the mod. No team ever holds more than four players: players leave teams before others join, and a join waits until the team has room.
- Above four players, the new **Teams above four players** option chooses between **Squads of 4** (default): every next four players get their own team (2, 3, …; team 1 is the game's AI team) and see their own squad, and **No teams**: everyone leaves their team, as before. Squads stay together when players leave; with four or fewer players left, everyone shares team 0 again.
- Teams are checked on every pass (2 s) and on every join; squad teams are recreated after seamless travel. Team sizes, without player names, are written to the runtime diagnostics and the SDK log.
- Checked with two players by moving them between teams with a probe, not with this code: the panel appears for both players in a shared team, including a new team 2, and survives fast travel; players in different teams cannot damage each other; enemy damage, revival, and entering each other's vehicles do not depend on teams.

## 1.2.0 — October 7, 2026

Removes a periodic host stutter. Patch data and hotfix registration are unchanged.

- Fix a host stutter every 2 seconds. Each check resolved all 39 records separately (26 full object scans) and rebuilt the diagnostics in one frame, blocking the game thread for 90–190 ms in the main menu. Each target is now resolved once per pass and passes run one target per frame. Diagnostics are rewritten only when they change.
- Full passes only follow map changes and player-count changes, at 0, 2, 6, 14, 30 and 62 s. In the five-player session every readback error (EffectiveNumPlayers, AdjustedNetSpeed recomputed by the game) followed a join or leave. Between full passes only unsettled targets and an unregistered hotfix service are retried every 2 s.
- Several map hooks fired by one map change (seamless travel fires a few within seconds) forget applied objects only once, so unchanged objects are no longer re-applied two or three times per map change.
- Measured in the main menu (about 200k objects): 20 hitches per 40 s before, none in 90 s after (117 FPS, as without the periodic pass). In a loaded map with two players, including a join and seamless travel: 117 FPS; a full pass costs one frame of about 18 ms against 8.5 ms normally, and none run between triggers. After a join, the readback errors were found within a second and fixed 2 s later. Not yet tested with more than two players.

## 1.1.0 — October 5, 2026

Publication preparation of the SDK adaptation tested October 4.

- Preserve Robeth v0.18 data and AstrandPallas's SDK PickTeam approach.
- Apply loaded targets, retry pending objects, and verify readback.
- Register hotfix pairs without losing existing entries, rejecting conflicts.
- Add runtime diagnostics, offline tests, portable installer/rollback and fullscreen launch, reproducible packaging, and CI.
- Document real five-player testing, item persistence, unresolved join freeze, and untested DLC/offline scenarios.

Imported runtime __init__.py SHA256:
26c4b3d23576d9e4e3a031fc8f78857d0494d5317441a9315c65d15f1c113031

Unchanged cooppatch.txt SHA256:
804f7f740ee2c1d0c5ca6a1e9dec5cbce4c9a6d3c7cf09407ff1c3b56b9712da

## Provenance

AstrandPallas SDK commit 9b2649ede66babe5a236dd59b0101c69da5e8b84; upstream latest-csharp 522d8e795b5711a1ab3929129e30924db48d4f46; original v0.18 patch data. Legacy C# code/history remains for reference; fixed offsets must not be applied to current files.
