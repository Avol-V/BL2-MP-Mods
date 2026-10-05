# Unlimited COOP for Borderlands 2 — SDK adaptation

An experimental **host-only** adaptation of Robeth's Unlimited COOP, based on AstrandPallas's PythonSDK port. Version **1.1.0** was tested with **five real players on separate computers** on Borderlands 2 CL2863302. It uses runtime SDK hooks and preserves the original v0.18 cooppatch.txt; it does not patch game executables or UPK files.

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

Do not install both the folder and a packed .sdkmod of this mod. Build an optional archive with python SDKMod/tools/build_package.py. The folder was tested in-game; the archive has only been checked offline.

## Play

If installed in the normal Steam game directory, **the normal Steam launch loads the SDK and mod**. No legacy patcher, special server executable, or manual exec cooppatch.txt is required. If using a separate copy, start that copy while Steam is running.

Optional fullscreen launch:

```powershell
& .\SDKMod\tools\Start-Game.ps1 -GameDirectory "C:\Program Files (x86)\Steam\steamapps\common\Borderlands 2" -Launch
```

It uses your configured resolution, opens no debug console, and exits immediately after starting the game. Omit -Launch to inspect the plan. Language is not forced; optionally pass -Language rus or another installed three-letter code. [Tools and rollback](docs/tools.md).

Load a map before clients join. Connect progressively to two, four, then five players; the fifth joins from the main menu into the loaded map. The stock lobby/HUD still has four slots; use actual participants/live game counts to verify joining. Disabling the mod requires a full game restart because applied runtime settings are not automatically reverted.

## Changes

- Retain AstrandPallas's PickTeam hook returning the requested team number.
- Apply commands when targets are loaded, retry pending targets, and invalidate identities on map changes without retaining UObject references across GC.
- Register 13 enabled hotfix records by Micropatch service identity, preserve unrelated entries, reject conflicts/ambiguous services, and verify arrays.
- Write readback, pending targets, live player counts, and hotfix status to sdk_mods/settings/unlimited_coop.runtime.json.
- Add offline tests, portable install/rollback and launch tools, a reproducible package builder, and CI.

The original settings include capacities of 64/512; **only five players were tested**. Offline hotfix registration is unverified. [Limitations](docs/testing.md).

## Development and provenance

Python 3.11+ is needed for tools/tests; the in-game runtime is supplied by the SDK.

```powershell
python -m unittest discover -s SDKMod/tests -v
python SDKMod/tools/build_package.py
```

CI runs offline tests and builds artifacts on Windows/Linux. It does not verify gameplay. Legacy patcher sources/history remain for reference; **do not apply their fixed offsets to current files**. [Historical README](docs/legacy-readme.md).

Based on [RobChiocchio/BL2-MP-Mods](https://github.com/RobChiocchio/BL2-MP-Mods) and the SDK addition in [AstrandPallas/BL2-MP-Mods](https://github.com/AstrandPallas/BL2-MP-Mods), commit 9b2649ede66babe5a236dd59b0101c69da5e8b84. Runtime logic matches the tested local adaptation; public metadata/tools were prepared afterward. [Changelog](CHANGELOG.md).

Licensed under the existing [GNU GPL v3](LICENSE). Credit to Robeth, AstrandPallas, the SDK maintainers, contributors listed in the historical README, and five-player test volunteers. This is an independent adaptation, not an official Gearbox release.
