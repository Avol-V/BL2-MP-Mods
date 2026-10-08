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

## Version 1.2.0 (October 7, 2026)

Same game and SDK builds, folder installation, host plus one client on a separate computer. Frame times were recorded in-game from PlayerTick intervals.

| Scenario | Result |
|---|---|
| Main menu, 1.1.0 | 111 FPS, a 90–190 ms hitch every 2.0 s; none with the periodic pass disabled (117 FPS) |
| Main menu, 1.2.0, 90 s | 117 FPS, no hitches, longest frame 15.5 ms |
| Two players, icecanyon_p and SanctuaryAir_P | Players noticed no stutter; 117 FPS |
| Client join during play | Readback errors found within a second, fixed 2 s later; PickTeam called |
| Load from the menu, seamless travel to Interlude_P | Commands re-applied once per map change |
| Steady state between triggers | No full passes; at most 0.4 ms of mod work per frame |

A hitch of about 20 ms every 60 s remained with no mod work or Python GC inside it; it matches the engine's TimeBetweenPurgingPendingKillObjects=60 and was not measured without the mod.

## Version 1.3.0 (October 8, 2026)

Same game and SDK builds, folder installation, host plus one client on a separate computer. Team state and whether the host's HUD would show the client were logged every 2 s by a separate in-game probe; players checked both screens.

| Scenario | Result |
|---|---|
| Up to 1.2.0, two players (October 7) | Host alone in team 0, client without a team; no ally panel on either screen |
| Same session, client moved to the host's team by a probe | Ally panel on both screens; also with both in a new team 2, kept after fast travel |
| Host and client in different teams (0 and 2), October 7 | No ally panel; no damage between players; enemy damage both ways and revival from Fight For Your Life work |
| Vehicles, host in team 0 and client without a team | Both enter each other's vehicles directly and by Catch-A-Ride teleport |
| 1.3.0: host in the main menu and after loading a map | Host in team 0 |
| 1.3.0: client joins SanctuaryAir_P | Client placed in team 0 on join; ally panel on both screens |
| Seamless travel to Interlude_P | Both stay in team 0, panel remains |
| Option switched four times during play, then twice alone | Logged mode changes; teams unchanged with up to four players, panel remains |
| Client leaves and rejoins | Panel returns. The first rejoin attempts did not connect until the client restarted their game; nothing was changed on the host, and the host log shows no errors. Cause not established |

More than two players, squads, and the No teams mode above four players are untested.

## Known issues

**One host restart froze when the first client joined.** Last sample: NumPlayers=2, EffectiveNumPlayers=2 instead of 4 (two records), AdjustedNetSpeed=7000 instead of 5000. Diagnostics stopped updating. Logs were preserved and the process stopped. A fresh run of the unchanged mod accepted all five. These mismatches do not establish the freeze cause. Short-lived readback errors during successful play followed every join (EffectiveNumPlayers twice, AdjustedNetSpeed) or leave (one error), values the game recomputes, and cleared on the next poll.

**Local multi-instance testing was abandoned.** Two copies crashed in bifrost.dll. A later attempt generated background SHiFT reconnections and a temporary restriction. SaveDataId did not prove separate profiles. Separate folders or LAN selection do not establish profile/account isolation. Real multiplayer testing used separate computers.

**Name tags above players broke at five players.** In the October 4 session, name tags froze at one screen position when the fifth player joined and disappeared after travel to another map, not returning. Without them it is hard to tell where the others are. With two players name tags work regardless of teams. The cause is unknown; 1.3.0 does not change it.

**No ally panel up to 1.2.0.** The HUD panel only shows teammates, and these versions left the host alone in team 0 and clients without a team. 1.3.0 assigns teams; tested with two players.

- Five players tested with 1.1.0, two with 1.2.0; six or more, advertised 64/512 capacities, long-term stability, and interactions with other gameplay mods are untested.
- Five-player DLC play remains unverified; solo DLC loading does not substitute.
- No unique Micropatch service means pending hotfix registration. Offline service creation was not implemented/verified. Do not repeatedly reconnect to force it.
- Original Players=99 in one KillSkillDuration expression is retained; its gameplay implications were not independently validated.
- Disabling needs a restart. Game copies share default saves/config; testing used disposable characters.
- Public installer/launcher/package tools were prepared and checked offline after the game test. For 1.1.0, runtime logic was imported without behavioral changes; the packed archive has not been tested in-game.

## Reproduce/report

Back up saves, match builds/DLC, use disposable characters, and test solo first. Join to two/four/five, with the fifth joining a loaded map from the main menu. Check movement/combat/revival/loot, travel, reconnecting, and persistence after clean exit/restart. Test DLC only when owned by everyone.

Preserve sdk_mods/settings/unlimited_coop.runtime.json, Binaries/Win32/Plugins/unrealsdk.log, and the game log before restarting. JSON is rewritten only on changes: its timestamp is not a heartbeat. Live logs may be buffered. Record the map, count, network mode, versions, sequence, and client error. Sanitize account IDs, addresses, and personal paths before posting logs. Raw logs, saves, and game binaries are not distributed here.

If a freeze repeats, preserve evidence and stop cyclic joining attempts. A successful retry is not a fix for an unresolved failure.
