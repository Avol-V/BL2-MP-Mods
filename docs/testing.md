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

## Version 1.4.0 (October 8, 2026)

Same game and SDK builds, folder installation unless noted, a disposable level 30 character. Teams were forced into squad team 2 by a probe that replaced the mod's team plan, travel events and vehicle state were logged by probes, and players checked both screens.

| Scenario | Result |
|---|---|
| Fast travel, also to a DLC map (Oasis), host alone | The GameInfo, its teams and the players' PRIs are kept: maps stream into the persistent Loader world. InitializeTeams and HandleSeamlessTravelPlayer are not called; team 2 stays as it was |
| Load from the main menu, host in team 2 | Seamless travel to a new Loader world: InitializeTeams creates team 2 in the new GameInfo, HandleSeamlessTravelPlayer moves the host into it, no later team changes |
| Same with a client who joined the menu lobby | The client joined straight into team 2. After loading, the host was moved by the game at once; the client, still loading, by the mod's next pass 0.1 s later, then nothing was left for the game. Ally panel on both screens |
| Debug command openl from a loaded map | The game crashed 3 s later in native Skill.AdjustModifiers, also with no squads, probes or vehicle options. Not used in normal play; not checked without the mod |
| Vehicle options switched by a probe and in the Mods menu | Applied on the next frame and saved; turning them off restored the stock values exactly |
| Any vehicle at any station, main-game station (Three Horns Divide) | Host: Bandit Technical, Runner, Sand Skiff, Fan Boat; spawned a Fan Boat (2 seats), Technical (4) and Runner (2). Option off: Technical and Runner. A client without the mod sees Technical and Runner |
| Stand on vehicles | The host stands on the Runner and Technical and slides off with the option off. A client without the mod stays on the host's Technical, also driven fast, with slight jitter: the client's game drops the vehicle as its base and the host restores it every 1–3 s |
| DLC station (Oasis) | Untested: the test character had not unlocked it. Its station definition loads with the map and was updated |
| Packed archive alone, no folder | Loaded, enabled, applied the patch and wrote diagnostics; the installer refuses a folder installation next to it |

Not tested: more than two players, real squads (five or more), DLC stations with the vehicle options, NoCap's issue #1 (lost controls after a "no vehicles" message at a DLC station).

## Version 1.5.0 (October 8, 2026)

Same game and SDK builds, folder installation, a disposable level 30 character in the first playthrough, maps Three Horns Divide (Ice_P) and Sanctuary. Values were read in game by a probe that evaluates the balance tables natively (AttributeInitializationDefinition.EvaluateInitializationData, the player controller as context, so a normal enemy). More than two players were simulated: the probe replaced the mod's player count, so the mod counted five, six or eight players while EffectiveNumPlayers and the tables followed.

| Scenario | Result |
|---|---|
| Alone, title screen and Ice_P | EffectiveNumPlayers 1; stock tables (enemy health 1.0, damage 0.65, gun damage 0.8); experience and kill skill rows stock, 64 rows; fast travel countdown 5 s; network values stock on the live net drivers |
| Counted five, alone | EffectiveNumPlayers 4; enemy health 2.05, damage 1.41, gun damage 1.65, shields 1.3, enemy vehicles 1.28, badass weight 3.0, boss weight 4; den formulas at their four-player values (More enemies off); network block on |
| Counted eight, strength 50%, More enemies on | Health 2.35, damage 1.60, gun damage 1.90, shields 1.6, vehicles 1.36, badass 3.5, bosses 5; den formulas: 6 and 7 extra enemies, linear formulas 7 (N − 1) and 2.75 (0.25 N + 0.75) |
| Back to one counted player | Every table and network value back to stock; nothing left in the diagnostics |
| Counted five, fast travel to Sanctuary and back | Tables loaded on each map continued again after loading, including tables reloaded with stock values |
| Instant fast travel on and off | Countdown 0 on both GlobalsDefinition objects, then their own stock values (3 for the class default, 5 for GD_Globals); travel started at once |
| Kill skill, alone | DurationOfLastKillSkillActivation 7 (the stock one-player row; the original patch set 1). With the mod counting five (EffectiveNumPlayers 4, one real player): 10, so the game picks the row by EffectiveNumPlayers |
| Two players: join, leave | EffectiveNumPlayers 2 at once on join and 1 at once on leave, set by the hooks (no pass had to fix it); both in team 0; stock two-player tables (health 1.2, damage 0.9, shields 1.1, badass 1.5) |
| Two players, mod counting five | Network block on the live net drivers (tick rate 20, client rates 7000/10000, timeouts 300/120) and on both existing PRIs (update frequency 20); the client noticed no disconnect or stutter while moving and shooting; switched back without disconnect. The client's net speed stayed 10000 both ways: the game only calls SetNetSpeed when its computed per-player rate changes, and that stays 7000 |
| Ini files | Up to 1.4.0 the network values had been saved into the user's WillowEngine.ini and WillowGame.ini. With 1.5.0 the files were rewritten by the game on exit with identical content. With those files 1.5.0 kept the stock values in memory up to four players; after restoring the files the game itself loads the stock values, and bClampListenServerTickRate is False without its line |

Not tested: more than two real players, enemies actually spawned above four players (health bars, den counts, missions with More enemies), UVHM (by the game data the stock playthrough attribute does not count a third playthrough, so UVHM takes the second-playthrough branches), DLC tables (witch doctors, Son of Crawmerax, wedding badasses, summoners: not loaded on the tested maps).

## Version 1.6.0 (October 9, 2026)

Same game and SDK builds, folder installation, the disposable level 30 character on Three Horns Divide (Ice_P). Its first discovered main-game station in another map is Claptrap's Place (Windshear Waste, Glacial_P). A probe killed every enemy near the station and compared the map's population trackers before the kill and after a reload; another probe compared every loaded population definition with the game data.

| Scenario | Result |
|---|---|
| Fast travel away and back, no reload | The map's trackers kept their saved state: opportunities that never respawn, and those still waiting for their respawn delay, stayed empty |
| Main menu | The Kismet bank and the population trackers are empty: a save-quit forgets the session state of every map. The reload forgets only the current map's |
| Reload alone, from the Mods menu | Waited while the menus were open, started when they closed. To Glacial_P, back 3.5 s after arriving, done 7.5 s after the start. All 28 opportunities that had actors before the kill had them again, including 5 that never respawn. Afterwards every loaded population definition and both class defaults had their game-data values, and the trackers their stock flags |
| Reload with two players | The client reported Glacial_P loaded before the travel back; 8 s in total. The client saw two short loading screens, no freeze or disconnect, and landed with the host on Ice_P; the same reset as alone |
| Client's inventory open | Refused: the game told both players who was in a menu, the host got the mod's message, nobody travelled |
| Travel back too early | A first build started the travel back before the other map had loaded; the game ignored it, the reload stopped after 90 s and restored the stock values |

Not tested: defend waves (population encounters) after a reload, reloads on DLC maps and in Sanctuary, more than two players, a client loading much slower than the host.

## Known issues

**One host restart froze when the first client joined.** Last sample: NumPlayers=2, EffectiveNumPlayers=2 instead of 4 (two records), AdjustedNetSpeed=7000 instead of 5000. Diagnostics stopped updating. Logs were preserved and the process stopped. A fresh run of the unchanged mod accepted all five. These mismatches do not establish the freeze cause. Short-lived readback errors during successful play followed every join (EffectiveNumPlayers twice, AdjustedNetSpeed) or leave (one error), values the game recomputes, and cleared on the next poll. Since 1.5.0 EffectiveNumPlayers=2 with two players is intended and AdjustedNetSpeed is not set.

**Up to 1.4.0 the network values were saved to the game's ini files** (WillowEngine.ini, WillowGame.ini in the user's documents), as running the original cooppatch.txt does: the console command set saves config properties. The game kept them without the mod and in other installations sharing the same documents folder. 1.5.0 saves nothing and ignores these values up to four players; the README lists the stock values to restore the files.

**Local multi-instance testing was abandoned.** Two copies crashed in bifrost.dll. A later attempt generated background SHiFT reconnections and a temporary restriction. SaveDataId did not prove separate profiles. Separate folders or LAN selection do not establish profile/account isolation. Real multiplayer testing used separate computers.

**Name tags above players broke at five players.** In the October 4 session, name tags froze at one screen position when the fifth player joined and disappeared after travel to another map, not returning. Without them it is hard to tell where the others are. With two players name tags work regardless of teams. The cause is unknown; 1.3.0 does not change it.

**No ally panel up to 1.2.0.** The HUD panel only shows teammates, and these versions left the host alone in team 0 and clients without a team. 1.3.0 assigns teams; tested with two players.

- Five players tested with 1.1.0, two with 1.2.0 to 1.6.0; six or more, advertised 64/512 capacities, long-term stability, and interactions with other gameplay mods are untested.
- Five-player DLC play remains unverified; solo DLC loading does not substitute.
- The balance above four players (tougher and more enemies) was checked by values only, with the mod counting more players than were present; how it plays with five or more players is untested.
- Up to 1.4.0, without a unique Micropatch service hotfix registration stayed pending. 1.5.0 registers no hotfixes.
- Up to 1.4.0 the original Players=99 in one KillSkillDuration row was retained and kill skills lasted 1 s. 1.5.0 writes the stock rows.
- Disabling needs a restart. Game copies share default saves/config; testing used disposable characters.
- Public installer/launcher/package tools were prepared and checked offline after the game test. For 1.1.0, runtime logic was imported without behavioral changes. Up to 1.3.0 the packed archive was named unlimited_coop-<version>.sdkmod and the SDK ignored it; since 1.4.0 it loads, tested alone.

## Reproduce/report

Back up saves, match builds/DLC, use disposable characters, and test solo first. Join to two/four/five, with the fifth joining a loaded map from the main menu. Check movement/combat/revival/loot, travel, reconnecting, and persistence after clean exit/restart. Test DLC only when owned by everyone.

Preserve sdk_mods/settings/unlimited_coop.runtime.json, Binaries/Win32/Plugins/unrealsdk.log, and the game log before restarting. JSON is rewritten only on changes: its timestamp is not a heartbeat. Live logs may be buffered. Record the map, count, network mode, versions, sequence, and client error. Sanitize account IDs, addresses, and personal paths before posting logs. Raw logs, saves, and game binaries are not distributed here.

If a freeze repeats, preserve evidence and stop cyclic joining attempts. A successful retry is not a fix for an unresolved failure.
