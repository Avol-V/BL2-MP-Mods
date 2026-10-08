# Unlimited COOP for Borderlands 2 — SDK adaptation

An experimental **host-only** adaptation of Robeth's Unlimited COOP, based on AstrandPallas's PythonSDK port. Version **1.1.0** was tested with **five real players on separate computers** on Borderlands 2 CL2863302. Version **1.2.0** only changes when settings are re-checked, removing a periodic host stutter, and was tested with two players. Version **1.3.0** assigns players to teams of up to four so the stock ally panel works; it was tested with two players, squads above four players are untested. Version **1.4.0** keeps squads when a game is loaded from the main menu and adds two optional vehicle tweaks from NoCap; it was tested alone and with two players. Version **1.5.0** balances up to four players as the unmodified game does and makes enemies tougher per player above four; it was tested alone and with two players, with more players simulated by a probe. It uses runtime SDK hooks and keeps the original v0.18 cooppatch.txt unchanged; it does not patch game executables or UPK files.

Five-player joining, map travel, damage, ally revival, the fifth player's active skill and item pickup, rejoining, and item persistence after restarting were confirmed on October 4, 2026. **One restart attempt froze when the first client joined; the next attempt succeeded without changing the mod. The cause remains unresolved.** Five-player DLC play is untested. See [test results](docs/testing.md).

## Install

1. Install the [willow2 PythonSDK mod manager](https://github.com/bl-sdk/willow2-mod-manager/releases). Manager **v3.8** was used in the test. Follow its instructions; this repository does not bundle the SDK or the game.
2. Back up saves and close Borderlands 2. For an isolated test, use a separate full game copy with the SDK installed. Copies still share the default user saves/config; they are not separate profiles.
3. Copy **only** SDKMod/unlimited_coop into <game>/sdk_mods/unlimited_coop.
4. Start the game and enable **Unlimited COOP** in Mods. Only the host enables this mod. Clients use the same game build and need the selected map's DLC.

Alternatively, use the [verified-backup installer](docs/tools.md) with Python 3.11+:

```powershell
python SDKMod/tools/install.py --game-dir "C:\Program Files (x86)\Steam\steamapps\common\Borderlands 2" --enable
python SDKMod/tools/install.py --game-dir "C:\Program Files (x86)\Steam\steamapps\common\Borderlands 2" --enable --apply
```

The first command is read-only; the second applies its plan. Replace the example path with your installation. The installer checks tested core hashes and SDK presence, preserves other settings, and backs up changed files. It does not install the SDK or alter saves. An unrecognized build requires explicit --allow-untested-build; this does not establish compatibility.

Alternatively, build SDKMod/dist/unlimited_coop.sdkmod with python SDKMod/tools/build_package.py and copy only that file into <game>/sdk_mods, keeping its name: the SDK ignores an archive whose name differs from its root folder. Do not install both the folder and the archive. The archive was loaded in-game alone with 1.4.0; multiplayer tests used the folder.

## Play

If installed in the normal Steam game directory, **the normal Steam launch loads the SDK and mod**. No legacy patcher, special server executable, or manual exec cooppatch.txt is required. If using a separate copy, start that copy while Steam is running.

Optional fullscreen launch:

```powershell
& .\SDKMod\tools\Start-Game.ps1 -GameDirectory "C:\Program Files (x86)\Steam\steamapps\common\Borderlands 2" -Launch
```

It uses your configured resolution, opens no debug console, and exits immediately after starting the game. Omit -Launch to inspect the plan. Language is not forced; optionally pass -Language rus or another installed three-letter code. [Tools and rollback](docs/tools.md).

Load a map before clients join. Connect progressively to two, four, then five players; the fifth joins from the main menu into the loaded map. The stock lobby still has four slots; use actual participants/live game counts to verify joining.

The HUD ally panel shows up to three teammates. Up to four players share one team, as in the unmodified game. Above four, the **Teams above four players** option in the Mods menu either forms squads of four (default: each player sees their own squad) or leaves everyone without a team, as before 1.3.0 (no ally panel). Name tags above players broke when a fifth player joined in the five-player test; see [known issues](docs/testing.md).

Up to four players the game is balanced as without the mod. Above four, **Stronger enemies above four players** (on by default) adds the game's own step from three to four players for every extra player: enemy health, damage and shields and the share of badass variants grow, the number of enemies does not. **Strength per extra player** (100% by default, 0–200%) scales that step. **More enemies above four players** (off by default) makes enemy dens and summoners spawn more enemies by the same rule; if a mission that waits for every enemy gets stuck, turn it off until the mission is done. **Instant fast travel** (off by default) removes the 5-second countdown, as the original patch did. The original patch's network settings (lower tick rates, higher bandwidth, longer timeouts) apply only above four players.

Two options from NoCap, both off by default, help more players ride along. **Stand on vehicles** lets players stand on top of every vehicle, not only on the Sand Skiff and Fan Boat. **Any vehicle at any station** makes Catch-A-Ride stations offer every vehicle family, such as the Sand Skiff or Fan Boat at a main-game station (seats in the test: Technical 4, Runner 2, Fan Boat 2). Only the host needs the mod: players without it see the stock vehicle list and jitter slightly while standing on a vehicle, but stay on it. DLC stations are untested.

Disabling the mod requires a full game restart because applied runtime settings are not automatically reverted.

### Network values left by versions up to 1.4.0

Up to 1.4.0, and with the original cooppatch.txt, the console command set also saved the patch's network values into the game's ini files in Documents\My Games\Borderlands 2\WillowGame\Config, and the game kept using them without the mod. 1.5.0 changes nothing on disk and uses the stock values up to four players even while the files still hold the patch's values. To restore the files for the game without the mod, close the game, back them up and edit:

- WillowGame.ini, [Engine.GameInfo]: TotalNetBandwidth=32000, MinDynamicBandwidth=4000.
- WillowEngine.ini, [Engine.Engine]: NetClientTicksPerSecond=200.
- WillowEngine.ini, [IpDrv.TcpNetDriver]: ConnectionTimeout=30.0, InitialConnectTimeout=60.0, KeepAliveTime=0.2, MaxClientRate=15000, MaxInternetClientRate=10000, SpawnPrioritySeconds=1.0, NetServerMaxTickRate=30; delete the bClampListenServerTickRate line.
- WillowEngine.ini, [OnlineSubsystemSteamworks.IpNetDriverSteamworks]: delete the lines bClampListenServerTickRate, NetServerMaxTickRate, MaxInternetClientRate, MaxClientRate, SpawnPrioritySeconds, KeepAliveTime, InitialConnectTimeout and ConnectionTimeout. The driver then takes the values of [IpDrv.TcpNetDriver], as in a fresh installation.

The values come from the game's BaseEngine.ini, DefaultEngine.ini and BaseGame.ini.

## Changes

- Assign teams through AstrandPallas's PickTeam hook: up to four players share team 0 as in the unmodified game; above four, squads of four or no teams (option). The ally panel has three slots and the game does not bounds-check them, so no team ever holds more than four players, even while players are moved between teams. Squad teams are recreated in the new GameInfo when a game is loaded from the main menu.
- Optional vehicle tweaks from NoCap: standing on vehicles and every vehicle at every Catch-A-Ride station, applied per map and per spawned vehicle, with stock values restored when turned off. Unlock requirements are unchanged.
- Keep EffectiveNumPlayers, which the game's balance reads, at min(players, 4) instead of the original patch's constant 4: stock balance up to four players, the four-player balance above.
- Continue the game's step from three to four players above four: tougher enemies (option, on by default, with a strength setting) and more enemies (option, off by default). Experience and kill skills keep their stock values.
- Use the original patch's lobby capacities always, its network settings above four players and its instant fast travel by option. Its hotfixes and the constant EffectiveNumPlayers are no longer applied; the health hotfix was wrong.
- Write values in memory where they differ, when their objects are loaded, and retry pending targets, without retaining UObject references across GC. Nothing is saved to ini files.
- Spread checks over frames: one target or table per frame, full passes only after map and player-count changes (a series over about a minute), and only unsettled targets retried every 2 s.
- Write readback, pending targets, player counts, options, the network block and changed tables to sdk_mods/settings/unlimited_coop.runtime.json.
- Add offline tests, portable install/rollback and launch tools, a reproducible package builder, and CI.

The original settings include capacities of 64/512; **only five players were tested**, and the balance above four players only with a probe that made the mod count more players. [Limitations](docs/testing.md).

## Development and provenance

Python 3.11+ is needed for tools/tests; the in-game runtime is supplied by the SDK.

```powershell
python -m unittest discover -s SDKMod/tests -v
python SDKMod/tools/build_package.py
```

CI runs offline tests and builds artifacts on Windows/Linux. It does not verify gameplay. Legacy patcher sources/history remain for reference; **do not apply their fixed offsets to current files**. [Historical README](docs/legacy-readme.md).

Based on [RobChiocchio/BL2-MP-Mods](https://github.com/RobChiocchio/BL2-MP-Mods) and the SDK addition in [AstrandPallas/BL2-MP-Mods](https://github.com/AstrandPallas/BL2-MP-Mods), commit 9b2649ede66babe5a236dd59b0101c69da5e8b84. Runtime logic matches the five-player test except for the check scheduling changed in 1.2.0, the teams added in 1.3.0, the squad and vehicle changes in 1.4.0 and the balance and network changes in 1.5.0, which have only had two-player tests so far; public metadata/tools were prepared afterward. [Changelog](CHANGELOG.md).

Licensed under the existing [GNU GPL v3](LICENSE). The vehicle options are adapted from [NoCap](https://github.com/stealmyhousekey/willow2-sdk-mods/tree/main/nocap) by stealmyhousekey (GPL-3.0). Credit to Robeth, AstrandPallas, stealmyhousekey, the SDK maintainers, contributors listed in the historical README, and five-player test volunteers. This is an independent adaptation, not an official Gearbox release.
