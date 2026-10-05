# Test results and limitations

## Environment

October 4, 2026: Windows host, BL2 Version 8639 / CL2863302 / build 257, Steam build 9218157, EXE FileVersion 1.0.257.2863302. SDK manager v3.8, unrealsdk 3.2.0, pyunrealsdk 1.10.0. Five real players on separate computers, folder installation of adaptation 1.1.0. A Russian localization was present; core EXE/UPK matched Steam depot data, but the full installation was not claimed byte-for-byte vanilla.

## Results

| Scenario | Result |
|---|---|
| Solo Commander Lilith SanctIntro_P | Loaded before multiplayer testing |
| Two players | Mutual visibility/movement confirmed, live NumPlayers=2 |
| Four players | Players confirmed working play, live NumPlayers=4 |
| Fifth joins SanctuaryAir_P | Confirmed by players and live NumPlayers=5 |
| Shared travel to icecanyon_p | All five remained connected |
| Damage and ally revival | Confirmed by players, not individually measured for every participant |
| Fifth exits/rejoins | Confirmed, live count returned to five |
| Fifth movement/shooting/skill/weapon pickup and inventory | Confirmed by players after rejoining |
| Full host restart | One join attempt froze; another full restart accepted all five |
| Item persistence | Picked-up items preserved, confirmed by players after restart |
| Five-player DLC | Skipped because one player lacked DLC; unverified |

Final restarted session on icecanyon_p: 35/39 command records read back, four pending, zero current errors, 13 registered hotfix records and 36 verified total service pairs. Counts came from the live GameInfo, excluding Default__ objects. Pending targets vary by map. Scalar readback is compared; structures are recorded without complete semantic comparison.

## Known issues

**One host restart froze when the first client joined.** Last sample: NumPlayers=2, EffectiveNumPlayers=2 instead of 4 (two records), AdjustedNetSpeed=7000 instead of 5000. Diagnostics stopped updating. Logs were preserved and the process stopped. A fresh run of the unchanged mod accepted all five. These mismatches do not establish the freeze cause. Short-lived readback errors also cleared on the next poll during successful play.

**Local multi-instance testing was abandoned.** Two copies crashed in bifrost.dll. A later attempt generated background SHiFT reconnections and a temporary restriction. SaveDataId did not prove separate profiles. Separate folders or LAN selection do not establish profile/account isolation. Real multiplayer testing used separate computers.

- Five players tested; six or more, advertised 64/512 capacities, long-term stability, and interactions with other gameplay mods are untested.
- Five-player DLC play remains unverified; solo DLC loading does not substitute.
- No unique Micropatch service means pending hotfix registration. Offline service creation was not implemented/verified. Do not repeatedly reconnect to force it.
- Original Players=99 in one KillSkillDuration expression is retained; its gameplay implications were not independently validated.
- Disabling needs a restart. Game copies share default saves/config; testing used disposable characters.
- Public installer/launcher/package tools were prepared and checked offline after the game test. Runtime logic was imported without behavioral changes; the packed archive has not been tested in-game.

## Reproduce/report

Back up saves, match builds/DLC, use disposable characters, and test solo first. Join to two/four/five, with the fifth joining a loaded map from the main menu. Check movement/combat/revival/loot, travel, reconnecting, and persistence after clean exit/restart. Test DLC only when owned by everyone.

Preserve sdk_mods/settings/unlimited_coop.runtime.json, Binaries/Win32/Plugins/unrealsdk.log, and the game log before restarting. JSON is rewritten only on changes: its timestamp is not a heartbeat. Live logs may be buffered. Record the map, count, network mode, versions, sequence, and client error. Sanitize account IDs, addresses, and personal paths before posting logs. Raw logs, saves, and game binaries are not distributed here.

If a freeze repeats, preserve evidence and stop cyclic joining attempts. A successful retry is not a fix for an unresolved failure.
