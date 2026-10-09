"""Robeth v0.18 lobby and network settings, team assignment through the PickTeam hook, balance by player
count (as in the unmodified game up to four players, continued above four), with load-aware application,
optional vehicle tweaks from NoCap, and a map reload for the host.

Experimental: runtime readback is not evidence of a successful fifth connection.
No package or executable offsets are used. Disabling requires a game restart.
"""
import hashlib
import json
import re
import time
from pathlib import Path

import unrealsdk
from unrealsdk import logging
from unrealsdk.hooks import Block, Type
from mods_base import (ENGINE, BoolOption, build_mod, ButtonOption, hook, open_in_mod_dir, RestartToDisable,
                       SliderOption, SpinnerOption)
from mods_base.settings import SETTINGS_DIR
from ui_utils import show_hud_message

__version__: str
__version_info__: tuple[int, ...]
SOURCE_SHA256 = '804f7f740ee2c1d0c5ca6a1e9dec5cbce4c9a6d3c7cf09407ff1c3b56b9712da'
HOTFIX = re.compile(r'^#<hotfix><key>"([^"]*)"</key><value>",(.*)"</value><(on|off)>$')
TYPED = re.compile(r"^\w+'(.+)'$")
SECTION = re.compile(r'^#<(/?)([^<>]+)>$')


def parse_patch(text):
    """Records of cooppatch.txt, each with the innermost #<SECTION> it is in."""
    records = []
    sections = []
    for raw in text.splitlines():
        line = raw.strip()
        section = SECTION.fullmatch(line)
        if section:
            if not section[1]:
                sections.append(section[2])
            elif sections and sections[-1] == section[2]:
                sections.pop()
            continue
        where = sections[-1] if sections else None
        match = HOTFIX.fullmatch(line)
        if match:
            key, body, state = match.groups()
            if state == 'off':
                continue
            target, prop, previous, value = body.split(',', 3)
            if previous:
                raise ValueError('Unsupported conditional hotfix: ' + key)
            typed = TYPED.fullmatch(target)
            target = typed[1] if typed else target
            records.append(dict(target=target, prop=prop, value=value, hotfix=key, section=where))
        elif line.lower().startswith('set '):
            if line.startswith(('set PlayerInput Bindings', 'set Transient.')):
                continue
            _, target, prop, value = line.split(None, 3)
            records.append(dict(target=target, prop=prop, value=value, hotfix=None, section=where))
    return records


# cooppatch.txt stays as published; the mod applies three of its sections. Lobby records always
# apply, network records above four players, the travel record by option.
LOBBY = 'lobby'
NETWORK = 'network'
TRAVEL = 'travel'
GROUPS = {'CORE - MORE PLAYERS': LOBBY, 'NETWORK OPTIMIZATION': NETWORK, 'INSTANT FAST TRAVEL': TRAVEL}
# Not applied: EffectiveNumPlayers 4 (it follows the player count, see set_effective), AdjustedNetSpeed
# (the game recomputes it on every join and leave), and every hotfix: with EffectiveNumPlayers at
# most four the game's own tables apply, the health fix was wrong, and experience and kill skills
# are written by apply_globals.
SKIPPED = ('EffectiveNumPlayers', 'AdjustedNetSpeed')
# Stock values of the network config properties, from the game's BaseEngine, DefaultEngine and
# BaseGame ini. Up to 1.4.0 the mod applied records with the console command set, which also saves
# config properties to the user's WillowEngine.ini and WillowGame.ini, as the original patch did; the
# game keeps them without the mod. A value equal to the patch value before the mod writes it is such a
# trace and gets the stock value. bClampListenServerTickRate is left out: it is not in the game's ini,
# and its class default is False, as in the patch.
NETWORK_STOCK = {name.lower(): value for name, value in dict(
    TotalNetBandwidth=32000, MinDynamicBandwidth=4000, NetServerMaxTickRate=30, KeepAliveTime=0.2,
    MaxInternetClientRate=10000, MaxClientRate=15000, SpawnPrioritySeconds=1.0, InitialConnectTimeout=60.0,
    ConnectionTimeout=30.0, NetClientTicksPerSecond=200.0).items()}


def select_records(patch):
    """The records the mod applies, each with its group."""
    return [dict(r, group=GROUPS[r['section']]) for r in patch
            if r['hotfix'] is None and r['section'] in GROUPS and r['prop'] not in SKIPPED]


with open_in_mod_dir(Path(__file__).with_name('cooppatch.txt'), binary=True) as stream:
    source = stream.read()
if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
    raise ValueError('Unexpected cooppatch.txt: review changes before enabling')
RECORDS = select_records(parse_patch(source.decode('utf8')))
# Record indices by target: a pass resolves each target once, not once per record.
TARGETS = {t: [i for i, r in enumerate(RECORDS) if r['target'] == t] for t in dict.fromkeys(r['target'] for r in RECORDS)}
CORE = {
    'WillowCoopGameInfo': ('MaxPlayers', 'MaxPlayersAllowed', 'EffectiveNumPlayers', 'NumPlayers'),
    'WillowOnlineGameSettings': ('NumPublicConnections', 'NumOpenPublicConnections'),
}
CHECK_INTERVAL = 2.0
# Full passes after a trigger at 0, 2, 6, 14, 30 and 62 s, then none until the next trigger.
FOLLOW_UP_MAX = 32.0
# The game's balance data covers one to four players: its tables branch on NumberOfPlayers, which
# reads EffectiveNumPlayers. Up to four players get the stock balance, above four the four-player
# one, which the difficulty options continue.
STOCK_PLAYERS = 4
# The HUD shows teammates in three ally slots and writes past them without a bound check, so five
# players in one team corrupt memory on every machine. With at most four per team, nobody sees
# more than three allies. Team 1 is the game's AI team; 255 is no team.
TEAM_LIMIT = 4
AI_TEAM = 1
NO_TEAM = 255
SQUADS = 'Squads of 4'
UNGROUPED = 'No teams'
team_mode = SpinnerOption(
    'Teams above four players', SQUADS, [SQUADS, UNGROUPED],
    description='Up to four players share one team as in the unmodified game, so the ally panel works.'
                ' Above four, Squads of 4 puts each next four players in their own team, and everyone'
                ' sees their own team in the ally panel. No teams leaves everyone without a team, like'
                ' the original patch: no ally panel.')
stronger_enemies = BoolOption(
    'Stronger enemies above four players', True,
    description='Up to four players enemies are balanced as in the unmodified game. Above four, each extra'
                " player raises enemy health, damage and shields and the share of badass variants by the game's"
                ' own step from three to four players. Enemy numbers are unchanged.')
enemy_strength = SliderOption(
    'Strength per extra player', 100, min_value=0, max_value=200, step=25,
    description="Percent of the game's step from three to four players that each player above four adds:"
                ' 100 is the step itself, 0 keeps enemies as for four players.')
more_enemies = BoolOption(
    'More enemies above four players', False,
    description="Above four players, enemy dens and summoners spawn more enemies, by the game's own step from"
                ' three to four players. Missions that wait for every enemy may take longer: if one gets'
                ' stuck, turn this off until it is done.')
instant_travel = BoolOption(
    'Instant fast travel', False,
    description='Fast travel without the stock 5-second countdown, as in the original patch.')
# Vehicle tweaks from NoCap (c) 2024-2025 stealmyhousekey, GPL-3.0, as two options, off by default.
stand_on_vehicles = BoolOption(
    'Stand on vehicles', False,
    description='Players can stand on top of every vehicle, not only on the Sand Skiff and Fan Boat, so more'
                ' players ride along. Players without this mod stay on but jitter slightly.'
                ' From NoCap by stealmyhousekey.')
any_vehicle_station = BoolOption(
    'Any vehicle at any station', False,
    description='Catch-A-Ride stations offer every vehicle family, such as the Sand Skiff and Fan Boat at'
                ' main-game stations. Unlocking is unchanged. Only players with this mod see the extra vehicles.'
                ' From NoCap by stealmyhousekey.')
# Values per definition class while its option is on. Tags are VSSUIDefinition.EVehicleSpawnStationAvailability:
# 0 Land, 1 Desert, 2 Ice, 4 Wheeled, 20 BL2Main. Every station turns into a main-game station, and every
# vehicle requires only what such a station supports.
VEHICLE_TWEAKS = {
    'ChassisDefinition': (stand_on_vehicles, dict(AllowPawnsToStandOnTopOfVehicle=True)),
    'VehicleSpawnStationGFxDefinition': (any_vehicle_station, dict(RequiredTags=[20], SupportedTags=[0, 4])),
    'VSSUIDefinition': (any_vehicle_station, dict(RequiredTags=[0, 20], SupportedTags=[0, 1, 2])),
    'VehicleFamilyDefinition': (any_vehicle_station, dict(RequiredTags=[0, 20], SupportedTags=[0, 1, 2])),
}
reload_map = ButtonOption(
    'Reload map', on_press=lambda _option: request_reload(),
    description='Host only, in a game. Reloads the map you are in as a save-quit does, and nobody is dropped:'
                ' after you close the menu everyone travels to a fast travel station you have discovered in'
                ' another map and back. Enemies, chests, vendors and scripted events of this map start over,'
                ' as after a save-quit; missions and the other maps keep their state.')
# Map reload. The game keeps a memory of every level visited in a session in two engine singletons
# that outlive travel and are empty in the main menu, which is why a save-quit brings enemies, loot and
# scripted events back and travel does not: population trackers (PopulationMaster.OpportunityList: the
# spawned, killed and looted actors of each opportunity) and the Kismet bank
# (PersistentGameDataManager.SequencesWithPersistentData: event trigger counts and Matinee positions by
# level package). A level forgets its trackers' saved state if its population definitions have
# bTotalResetOnLevelLoad when the level loads; the trackers' own copy of the flag is overwritten then.
# Checked in game 2026-10-09: enemies killed before leaving were back after the return only with the
# flag set while the map loaded, and the map left in between kept its state.
POPULATION_CLASSES = ('PopulationDefinition', 'WillowPopulationDefinition')
# Population definitions whose game data sets bTotalResetOnLevelLoad (BLCMM object dumps of BL2 with its
# DLC; matched every loaded definition in game): the stock value of a definition that first loads while
# the reload sets the flag. All others are False, as their class defaults.
RESET_ON_LOAD = frozenset((
    'GD_Allium_Lootables.Population.Pop_LootCar', 'GD_Anemone_AutoCannon.Population.PopDef_Anemone_AutoCannon',
    'GD_Anemone_Hector.InteractiveObjects.Anemone_PoP_HectorDead',
    'GD_Anemone_Hector.InteractiveObjects.Anemone_PoP_Hector_Flower',
    'GD_Anemone_InfectedPodTendril.Population.PopDef_InfectedPodTendril_RespawnOnLoad',
    'GD_Anemone_InfectedPod_Badass.Population.PopDef_InfectedPodTendril_Badass_SpawnOnLoad',
    'GD_Anemone_Pop_Bandits.Population.PopDef_MarauderBadass_Leader',
    'GD_Anemone_Pop_Bandits.Population.PopDef_NomadBadass_Leader',
    'GD_Anemone_Pop_Cassius.GD_Anemone_PopDef_Cassius',
    'GD_Anemone_Pop_Infected.Population.PopDef_InfectedBanditsMIX_Basic_RespawnOnLoad',
    'GD_Anemone_Pop_Infected.Population.PopDef_InfectedGolem_RespawnOnLoad',
    'GD_Anemone_Pop_Infected.Population.PopDef_InfectedMIX_Cavern_M030',
    'GD_Anemone_Pop_Infected.Population.PopDef_InfectedMIX_OldDust_SpawnOnLoad',
    'GD_Anemone_Pop_Infected.Population.PopDef_Infected_Gargantuan_SpawnOnLoad',
    'GD_Anemone_Pop_NP.Population.PopDef_NPMIX_Grunts_M030', 'GD_Anemone_Pop_NP.Population.PopDef_NP_Lt_Angvar',
    'GD_Anemone_Pop_NP.Population.PopDef_NP_Lt_Tetra',
    'GD_Anemone_Pop_NP.Population.PopDef_NewPandoraMIX_Grunts_SpawnOnLoad',
    'GD_Anemone_Pop_NP.Population.PopDef_SniperBase_M030',
    'GD_Anemone_Pop_WildLife.Population.PopDef_SandWorm_Queen',
    'GD_Anemone_Population_Treasure.Lootables.Brothers_Pile',
    'GD_Anemone_Population_Treasure.Lootables.Infected_Flower_LootBulb',
    'GD_Anemone_Population_Treasure.Lootables.ScrapPile',
    'GD_Anemone_Population_Treasure.Lootables.StalkerPileCeiling_Infected',
    'GD_Anemone_Population_Vehicles.Population.PopDef_Anemone_Technical_Mix',
    'GD_Anemone_Side_SpaceCowboy.InteractiveObjects.Pop_ToiletMidget',
    'GD_Anemone_StolenTurret.Balance.PopDef_Anemone_StolenTurret',
    'GD_Aster_EridiumSlotMachine.Populations.Pop_EridiumSlotMachine',
    'GD_Aster_Lootables.Balance.PopDef_DiceChestNoSaveState', 'GD_EasterEggs.Lootables.WhatsInTheBox',
    'GD_ElectricFence.PopDef.Pop_ElectricalFenceBox', 'GD_Episode09Data.Populations.Pop_Ep9_DeployedBeacon',
    'GD_Episode13Data.Populations.Pop_Ep13_EridiumHoseCoupling',
    'GD_Episode13Data.Populations.Pop_Ep13_FirstEridiumHoseCoupling',
    'GD_Flax_Lootables.Population.Pop_JackOLantern', 'GD_Flax_Lootables.Population.Pop_JackOLantern_Random',
    'GD_Flax_Lootables.TreasureChests.CauldronChest_Red', 'GD_Iris_SlotMachine.Populations.Pop_Iris_SlotMachine',
    'GD_Matchstick.Balance.PopDef_Matchstick', 'GD_Nasturtium_Lootables.InteractiveObjects.PopDef_NastChest_Ammo',
    'GD_Nasturtium_Lootables.Population.Pop_EasterEgg', 'GD_Orchid_Hovercraft.AI.PopDef_Hovercraft_Rider',
    'GD_Orchid_PlotDataMission04.Mission04.PopDef_Orchid_SandmanChest',
    'GD_Orchid_Pop_Loader.Population.PopDef_Orchid_LoaderBadass_Caravan',
    'GD_Orchid_Pop_RakkHive.Character.PopDef_Orchid_RakkHive',
    'GD_Orchid_PopulationVehicles.Flatbed.PopDef_Caravan_Flatbed',
    'GD_Orchid_SM_Scurvy_Data.Pop_Orchid_FruitTree1', 'GD_Orchid_SM_Scurvy_Data.Pop_Orchid_FruitTree2',
    'GD_Orchid_TreasureChests.InteractiveObjects.PopDef_PirateChest_Ammo',
    'GD_Orchid_TreasureChests.InteractiveObjects.PopDef_PirateChest_EndGame',
    'GD_Population_Treasure.Lootables.BugMorphPile', 'GD_Population_Treasure.Lootables.BullymongPile',
    'GD_Population_Treasure.Lootables.BullymongPile_AlwaysHealth',
    'GD_Population_Treasure.Lootables.CrystalPile_1', 'GD_Population_Treasure.Lootables.ScrapPile',
    'GD_Population_Treasure.Lootables.SkagPile', 'GD_Population_Treasure.Lootables.SpiderantPile',
    'GD_Population_Treasure.Lootables.StalkerPileCeiling', 'GD_Population_Treasure.Lootables.StalkerPileGround',
    'GD_Population_Treasure.Lootables.StalkerPilePillar',
    'GD_Population_Treasure.LootablesTrap.BugMorph.ScrapPile_BugMorph',
    'GD_Population_Treasure.LootablesTrap.MidgetHyperion.StalkerPileCeiling_MidgetHyperion',
    'GD_Population_Treasure.LootablesTrap.MidgetHyperion.StalkerPilePillar_MidgetHyperion',
    'GD_Population_Vehicles.Population.PopDef_CannonTurret',
    'GD_Sage_Lootables.Balance.PopDef_HyperionChest_EndGame', 'GD_Sage_Pop_Drifter.Population.PopDef_DrifterRaid',
    'GD_Sage_PopulationVehicles.VehicleCrew.PopDef_VehicleCrew',
    'GD_Z1_HandsomeJackHereData.Lootables.BullymongPile_Echo', 'GD_Z2_TheBankJobData.Lootables.TheBankJob_Toilet',
    'GD_Z3_UncleTeddyData.Lootables.CashBox_UncleTeddy',
    'GD_Z3_UncleTeddyData.Lootables.Storage_Locker_UncleTeddy',
    'GD_Z3_UncleTeddyData.Lootables.StrongBox_Recorder', 'gd_slotmachine.Populations.Pop_SlotMachine',
))
RELOAD_STEP = 0.5
# Longest wait for each travel and for everyone to be ready on the other map.
RELOAD_WAIT = 90.0
# Wait for the populations of the home map to connect after the host arrives there.
RELOAD_SETTLE = 10.0
# Clients count as loaded once they report the other map visible (ServerUpdateLevelVisibility; in game the
# host reports too). If the hook sees no report at all, clients get this long after the host arrives.
RELOAD_GRACE = 20.0
# Map names a station may stand for: a travel to Sanctuary_P lands in SanctuaryAir_P after the lift-off.
MAP_ALIASES = {'sanctuary_p': 'sanctuaryair_p'}
NOT_A_MAP = ('menumap', 'loader', 'fakeentry')
# Experience shares and kill skill durations by player count in GD_Globals, loaded from the start. The
# stock rows cover 1-4 players. The game picks the kill skill row by EffectiveNumPlayers (in game: 7 s
# alone, 10 s with EffectiveNumPlayers 4 and one player); rows for 5-64 repeat the four-player row, in
# case anything picks rows by NumPlayers. The original patch set 0.8 / 0.06 and 1 s for every count.
GLOBALS = 'GD_Globals.General.Globals'
PLAYER_ROWS = 64
GLOBAL_ROWS = (
    ('ExpAwardWeights', 'ExpAwardWeight', ('KillerExpBonus', 'ExpWeight'),
     ((0.0, 1.0), (0.04, 0.9), (0.05, 0.85), (0.06, 0.8))),
    ('KillSkillDurationsPerPlayers', 'KillSkillDuration', ('Duration',), ((7.0,), (8.0,), (9.0,), (10.0,))),
)
NUMBER_OF_PLAYERS = 'D_Attributes.GameProperties.NumberOfPlayers'
# AttributeExpression.EComparisonOperator: OPERATOR_EqualTo, OPERATOR_GreaterThanOrEqual.
EQUAL = 0
AT_LEAST = 5
STRONGER = 'stronger'
MORE = 'more'
# Balance tables (AttributeInitializationDefinition) continued above four players, by option. Tables
# whose step from three to four players is zero are left out. The first four load in Sanctuary;
# others load with combat or DLC maps.
TABLES = {
    # health, damage and shields of enemies, health of enemy vehicles
    'GD_Balance.WeightingPlayerCount.Enemy_HealthBoost_PerPlayerPerPlaythroughByChampion': STRONGER,
    'GD_Balance.WeightingPlayerCount.Enemy_Damage_PerPlayerPerPlaythroughByChampion': STRONGER,
    'GD_Globals.Balance.Init_EnemyGunDamage': STRONGER,
    'GD_Balance_HealthAndDamage.Shields.Init_EnemyShield_AdditionalShieldCapacityPerPlayer': STRONGER,
    'GD_BanditTechnical.HealthMultipliers.Init_EnemyVehicleHealthBoost_PerPlayerAndPlaythrough': STRONGER,
    # weights of badass and boss variants in population mixes
    'GD_Balance.WeightingPlayerCount.Enemy_MajorUpgrade_PerPlayer': STRONGER,
    'GD_Balance.WeightingPlayerCount.Enemy_Playthrough2OnlyBadass': STRONGER,
    'GD_Balance.WeightingPlayerCount.Bosses_PerPlayers': STRONGER,
    'GD_Sage_Pop_Natives.WeightingPlayerCount.WitchDoctors_PerPlayers': STRONGER,
    'GD_Population_VDay.WeightingPlayerCount.VDayWedding_BadassAdds_PerPlayer': STRONGER,
    # enemies added to dens: step formulas, then linear ones
    'GD_Balance.PlayerCountFormulas.Formula_Add2In2PlayerAnd3In4Player': MORE,
    'GD_Balance.PlayerCountFormulas.Formula_AddOneIn2PlayerAndTwoIn4Player': MORE,
    'GD_Balance.PlayerCountFormulas.Formula_Add1PerAdditionalPlayer': MORE,
    'GD_Balance.PlayerCountFormulas.Formula_ScaleBy25PercentPerAdditionalPlayer': MORE,
    # enemies summoned by Constructors and wizards, spawned in the Son of Crawmerax fight
    'GD_Balance.WeightingPlayerCount.Constructor_EnemySpawned': MORE,
    'GD_Balance.WeightingPlayerCount.Constructor_TotalEnemySpawned': MORE,
    'GD_WizardShared.WeightingPlayerCount.FireMage_EnemySpawned': MORE,
    'GD_WizardShared.WeightingPlayerCount.Necro_EnemySpawned': MORE,
    'GD_Crawmerax_Son.WeightingPlayerCount.CrawmeraxMission_EnemySpawned': MORE,
    'GD_Crawmerax_Son.WeightingPlayerCount.CrawmeraxMission_EnemyCrabsSpawned': MORE,
    'GD_Crawmerax_Son.WeightingPlayerCount.CrawmeraxMission_EnemyFireBugsSpawned': MORE,
}
# Gearbox's shield table tests "== 6" where four players were meant, so four players get the default
# 1.0, not 1.6. Above four the branch tests "== 4" and starts from 1.0: 1.3, 1.6, 2.2 for 5, 6, 8.
TYPOS = {'GD_Balance_HealthAndDamage.Shields.Init_EnemyShield_AdditionalShieldCapacityPerPlayer': 6.0}
_rows = {}
_stock = {}
_written = set()
_core = {}
_queue = []
_next_check = 0.0
_next_full = 0.0
_full_delay = CHECK_INTERVAL
_world = None
_players = None
_extra = 0
_effective_fixes = 0
_players_status = {'status': 'pending'}
_last_players_status = None
_globals_status = {'status': 'pending'}
_tables = {}
_table_stock = {}
_pick_calls = 0
_last_summary = None
_last_report = None
_teams_status = {'status': 'pending'}
_last_teams_status = None
_player_class = None
_squad_teams = set()
_vehicle_options = None
_vehicle_stock = {}
_vehicles_status = {}
_reload = None


def resolve(target):
    try:
        cls = unrealsdk.find_class(target)
    except ValueError:
        return [unrealsdk.find_object('Object', target)]
    return list(unrealsdk.find_all(cls, False))


def controller():
    """The local player's controller, on a client too: vehicle options apply there, nothing else does."""
    players = ENGINE.GamePlayers
    if not players or players[0] is None:
        return None
    pc = players[0].Actor
    if pc is None or pc.WorldInfo is None:
        return None
    return pc


def is_host(pc):
    return int(pc.WorldInfo.NetMode) != 3


def snapshot(pc):
    """Write diagnostics when they change; core values come from the last full pass."""
    global _last_report
    report = dict(version=__version__, world=pc.WorldInfo._path_name(), map=pc.WorldInfo.GetMapName(True), net_mode=int(pc.WorldInfo.NetMode),
                  source_sha256=SOURCE_SHA256, pick_team_calls=_pick_calls, teams=_teams_status,
                  players=_players_status,
                  options=dict(stronger_enemies=bool(stronger_enemies.value), strength=enemy_strength.value,
                               more_enemies=bool(more_enemies.value), instant_travel=bool(instant_travel.value)),
                  globals=_globals_status, tables={p: _tables[p] for p in TABLES if p in _tables},
                  vehicles=dict(_vehicles_status), core={cls: _core.get(cls, []) for cls in CORE},
                  records=[_rows[i] for i in sorted(_rows)],
                  caveat='Pending targets are not applied. Readback is not a 5+ multiplayer test.')
    if report == _last_report:
        return
    dest = SETTINGS_DIR / 'unlimited_coop.runtime.json'
    temp = dest.with_suffix('.tmp')
    temp.write_text(json.dumps(report, indent=2), encoding='utf8')
    temp.replace(dest)
    _last_report = report


def player_count(game):
    """Players the balance and the network block follow. A probe may replace it to test 5+ players alone."""
    return game.NumPlayers


def set_effective(game):
    """EffectiveNumPlayers = min(players, 4). The game sets it to NumPlayers; above four, its tables with
    "== 4" branches would fall back to their defaults, such as minimum health for player vehicles.
    Returns whether it had to change."""
    effective = min(player_count(game), STOCK_PLAYERS)
    if game.EffectiveNumPlayers == effective:
        return False
    game.EffectiveNumPlayers = effective
    return True


def apply_players(pc):
    """Fallback of players_changed on every pass, and the player counts for diagnostics."""
    global _effective_fixes, _players_status, _last_players_status
    game = pc.WorldInfo.Game
    if game is None:
        return
    try:
        _effective_fixes += set_effective(game)
        status = dict(NumPlayers=game.NumPlayers, counted=player_count(game),
                      EffectiveNumPlayers=game.EffectiveNumPlayers, network=group_on(NETWORK),
                      fixed_by_pass=_effective_fixes)
    except Exception as exc:
        status = dict(error=str(exc))
    _players_status = status
    if status != _last_players_status:
        logging.info(f'Unlimited COOP players: {status}')
        _last_players_status = status


def group_on(group):
    """Whether a group of records gets the patch values now; otherwise it gets the stock values."""
    return group == LOBBY or (group == NETWORK and _extra > 0) or (group == TRAVEL and bool(instant_travel.value))


def typed(value, like):
    """A patch value as the type of the property it goes to."""
    if isinstance(like, bool):
        return value.lower() == 'true'
    return int(float(value)) if isinstance(like, int) else float(value)


def same(actual, value):
    """Readback equality: numbers within float serialization tolerance, other values as text."""
    try:
        return abs(float(actual) - float(value)) < 0.0001
    except (TypeError, ValueError):
        return str(actual).lower() == str(value).lower()


def stock_of(kept, obj, current, written, record):
    """An object's stock value of a record, kept by path from first sight: its value then, before the mod
    wrote the record, unless it is a trace of an older version (NETWORK_STOCK). After that a new instance
    copied its archetype, which the mod changed, so it gets the archetype's stock value: GameInfo after
    a map load, the PRI of a joining player."""
    path = obj._path_name()
    if path not in kept:
        archetype = obj.ObjectArchetype if written else None
        inherited = None if archetype is None else kept.get(archetype._path_name())
        stock = NETWORK_STOCK.get(record['prop'].lower()) if record['group'] == NETWORK else None
        if inherited is not None:
            kept[path] = inherited
        elif stock is not None and same(current, record['value']):
            kept[path] = typed(str(stock), current)
        else:
            kept[path] = current
    return kept[path]


def settled(index):
    row = _rows.get(index, {})
    return row.get('status') == 'read_back' and row.get('on') == group_on(RECORDS[index]['group'])


def fail(target, status, exc):
    for index in TARGETS[target]:
        record = RECORDS[index]
        _rows[index] = dict(target=target, prop=record['prop'], group=record['group'], status=status, detail=str(exc))
    _core.pop(target, None)


def apply_target(pc, target):
    """Resolve one target (a full GObjects scan for classes) and bring its records to the values wanted now:
    the patch value while the record's group is on, otherwise each object's stock value. Only objects
    that differ are written: with stock values in place, nothing is written up to four players."""
    try:
        objects = resolve(target)
        if not objects:
            raise ValueError('No loaded instances')
    except ValueError as exc:
        return fail(target, 'pending', exc)
    except Exception as exc:
        return fail(target, 'error', exc)
    wrote = False
    for index in TARGETS[target]:
        record = RECORDS[index]
        prop, on = record['prop'], group_on(record['group'])
        row = dict(target=target, prop=prop, group=record['group'], on=on)
        try:
            kept = _stock.setdefault(index, {})
            written = index in _written
            readback = []
            for obj in objects:
                current = getattr(obj, prop)
                stock = stock_of(kept, obj, current, written, record)
                value = typed(record['value'], current) if on else stock
                if not same(current, value):
                    setattr(obj, prop, value)
                    _written.add(index)
                    wrote = True
                    current = getattr(obj, prop)
                    if not same(current, value):
                        raise RuntimeError(f'Readback differs: {obj._path_name()} {current!r} != {value!r}')
                readback.append(str(current))
            row.update(status='read_back', objects=[o._path_name() for o in objects], values=readback)
        except Exception as exc:
            row.update(status='error', detail=str(exc))
        _rows[index] = row
    game = pc.WorldInfo.Game
    if wrote and target == 'WillowCoopGameInfo' and game is not None:
        game.UpdateNetSpeeds()  # client net speeds follow TotalNetBandwidth now, as after a join or leave
    if target in CORE:
        _core[target] = [dict(path=o._path_name(), **{p: getattr(o, p) for p in CORE[target]}) for o in objects]


def player_rows(stock):
    """Rows for 1 to PLAYER_ROWS players: the stock rows for 1-4, then the four-player row."""
    return [(players, *stock[min(players, len(stock)) - 1]) for players in range(1, PLAYER_ROWS + 1)]


def rows_of(obj, prop, fields):
    return [(row.Players, *(getattr(row, f) for f in fields)) for row in getattr(obj, prop)]


def same_rows(actual, wanted):
    return len(actual) == len(wanted) and all(same(a, w) for x, y in zip(actual, wanted) for a, w in zip(x, y))


def apply_globals(_pc):
    """Write the experience and kill skill rows of GLOBAL_ROWS where they differ, and read them back."""
    global _globals_status
    try:
        obj = unrealsdk.find_object('GlobalsDefinition', GLOBALS)
        changed = []
        for prop, struct, fields, stock in GLOBAL_ROWS:
            wanted = player_rows(stock)
            if not same_rows(rows_of(obj, prop, fields), wanted):
                setattr(obj, prop, [unrealsdk.make_struct(struct, **dict(zip(('Players', *fields), row)))
                                    for row in wanted])
                changed.append(prop)
                if not same_rows(rows_of(obj, prop, fields), wanted):
                    raise RuntimeError(f'Readback differs: {prop}')
        status = dict(status='read_back', rows=PLAYER_ROWS, changed=changed)
    except ValueError as exc:
        status = dict(status='pending', detail=str(exc))
    except Exception as exc:
        status = dict(status='error', detail=str(exc))
    if status.get('changed') or status['status'] != _globals_status.get('status'):
        logging.info(f'Unlimited COOP globals: {status}')
    _globals_status = status


def player_condition(conditions):
    """The only condition of a branch on NumberOfPlayers as (index, operator, constant), None if it has
    not exactly one, and the branch's other conditions."""
    players = [(j, c[1], c[2]) for j, c in enumerate(conditions) if c[0] == NUMBER_OF_PLAYERS]
    return (players[0] if len(players) == 1 else None), tuple(c for c in conditions if c[0] != NUMBER_OF_PLAYERS)


def table_values(table, extra, strength, typo=None):
    """Values of the slots of a balance table that the mod continues for `extra` players above four:
    {slot: value}, with extra 0 the stock values, which restore them.

    table: stock data from read_table. Slots: ('value', i) is the value of branch i, ('operand', i, j) the
    constant of its condition j, ('offset',) the offset of a linear formula. Each four-player branch
    ("== 4" or ">= 4" on NumberOfPlayers) adds the game's own step from the three-player branch with the
    same other conditions (champion, playthrough) once per extra player, times strength. The game takes
    the first matching branch, so a repeated branch is left alone. A "== typo" branch stands for four
    players, who get the default value: above four it tests "== 4" and starts from the default. A
    linear formula Multiplier * (Level + Offset), Level = NumberOfPlayers * scale, moves its offset by
    scale per extra player, times strength.
    """
    threes = {}
    for value, conditions in table['rows']:
        player, others = player_condition(conditions)
        if player and player[1:] == (EQUAL, 3.0) and value is not None:
            threes.setdefault(others, value)
    values = {}
    seen = set()
    for i, (value, conditions) in enumerate(table['rows']):
        player, others = player_condition(conditions)
        if not player or value is None or others not in threes or conditions in seen:
            continue
        j, operator, constant = player
        if (operator, constant) in ((EQUAL, 4.0), (AT_LEAST, 4.0)):
            four = value
        elif typo is not None and (operator, constant) == (EQUAL, typo):
            four = table['default']
            values[('operand', i, j)] = 4.0 if extra else constant
        else:
            continue
        seen.add(conditions)
        values[('value', i)] = round(four + (value - threes[others]) * extra * strength, 6) if extra else value
    if table['formula']:
        offset, scale = table['formula']
        values[('offset',)] = round(offset + scale * extra * strength, 6)
    return values


def read_table(obj):
    """A balance table as plain data: branches as (value, conditions), the value None unless constant,
    conditions as (attribute path, operator, constant), the constant None if compared to an attribute;
    the default value; the offset and level scale of a linear formula on NumberOfPlayers, if any."""
    data = obj.ConditionalInitialization
    rows = []
    if data.bEnabled:
        for branch in data.ConditionalExpressionList:
            base = branch.BaseValueIfTrue
            constant = (base.BaseValueAttribute is None and base.InitializationDefinition is None
                        and base.BaseValueScaleConstant == 1)
            conditions = tuple((None if e.AttributeOperand1 is None else e.AttributeOperand1._path_name(),
                                int(e.ComparisonOperator), e.ConstantOperand2 if e.AttributeOperand2 is None else None)
                               for e in branch.Expressions)
            rows.append((base.BaseValueConstant if constant else None, conditions))
    formula = obj.ValueFormula
    level, power, offset = formula.Level, formula.Power, formula.Offset
    linear = (formula.bEnabled and level.BaseValueAttribute is not None
              and level.BaseValueAttribute._path_name() == NUMBER_OF_PLAYERS
              and power.BaseValueAttribute is None and power.BaseValueConstant == 1
              and offset.BaseValueAttribute is None)
    return dict(rows=rows, default=data.DefaultBaseValue.BaseValueConstant,
                formula=(offset.BaseValueConstant, level.BaseValueScaleConstant) if linear else None)


def table_slot(obj, slot):
    """The struct and field of a table slot, looked up again for each access."""
    if slot[0] == 'offset':
        return obj.ValueFormula.Offset, 'BaseValueConstant'
    branch = obj.ConditionalInitialization.ConditionalExpressionList[slot[1]]
    if slot[0] == 'value':
        return branch.BaseValueIfTrue, 'BaseValueConstant'
    return branch.Expressions[slot[2]], 'ConstantOperand2'


def table_key(group):
    """(players above four, strength) that a group of tables follows now: (0, 0.0) while its option is off."""
    if not _extra or not (stronger_enemies if group == STRONGER else more_enemies).value:
        return 0, 0.0
    return _extra, (enemy_strength.value / 100 if group == STRONGER else 1.0)


def table_due(path, full):
    """A table needs a step while its group continues it or its stock values wait to be restored: in full
    passes, and in light ones until it is read back with the values wanted now."""
    key = table_key(TABLES[path])
    if not key[0] and path not in _table_stock:
        _tables.pop(path, None)  # stock and untouched: nothing to restore or report
        return False
    status = _tables.get(path, {})
    return full or status.get('status') != 'read_back' or (status['above_four'], status['strength']) != key


def apply_table(_pc, path):
    """Continue one balance table for the players above four, or restore its stock values.

    Changed values apply to enemies that spawn afterwards. Stock data is kept by path from the first
    edit and forgotten once restored, or if the table is not loaded: it loads again with stock values.
    """
    group = TABLES[path]
    extra, strength = table_key(group)
    status = dict(group=group, above_four=extra, strength=strength)
    try:
        obj = unrealsdk.find_object('AttributeInitializationDefinition', path)  # a cheap lookup by name
        if path not in _table_stock:
            _table_stock[path] = read_table(obj)
        values = table_values(_table_stock[path], extra, strength, TYPOS.get(path))
        changed = 0
        for slot, value in values.items():
            holder, field = table_slot(obj, slot)
            if not same(getattr(holder, field), value):
                setattr(holder, field, value)
                changed += 1
                holder, field = table_slot(obj, slot)
                if not same(getattr(holder, field), value):
                    raise RuntimeError(f'Readback differs: {slot}')
        status.update(status='read_back', changed=changed,
                      values={' '.join(map(str, slot)): round(v, 4) for slot, v in values.items()})
    except ValueError as exc:
        status.update(status='pending', detail=str(exc))
    except Exception as exc:
        status.update(status='error', detail=str(exc))
    if not extra and status['status'] != 'error':
        _table_stock.pop(path, None)
    _tables[path] = status


def report(pc):
    global _last_summary
    records = tuple(sum(r['status'] == s for r in _rows.values()) for s in ('read_back', 'pending', 'error'))
    tables = {}
    for status in _tables.values():  # e.g. 'stronger +1 read_back': tables continued for one extra player
        key = f"{status['group']} +{status['above_four']} {status['status']}"
        tables[key] = tables.get(key, 0) + 1
    summary = (records, _globals_status['status'], tuple(sorted(tables.items())))
    if summary != _last_summary:
        logging.info(f'Unlimited COOP: read back {records[0]}/{len(RECORDS)}, pending {records[1]}, errors {records[2]};'
                     f' globals {summary[1]}; tables {tables or "untouched"}. Details: settings/unlimited_coop.runtime.json')
        _last_summary = summary
    snapshot(pc)


def plan_teams(current, mode):
    """Team index for each player, given their current indices (None: no team).

    Up to TEAM_LIMIT players share team 0, as in the unmodified game. Above that, UNGROUPED leaves
    everyone without a team (the original patch); SQUADS keeps players in their teams of at most
    TEAM_LIMIT and puts the rest into the first team with room: 0, 2, 3...
    """
    if len(current) <= TEAM_LIMIT:
        return [0] * len(current)
    if mode != SQUADS:
        return [None] * len(current)
    counts = {}
    plan = []
    for index in current:
        keep = index is not None and index != AI_TEAM and counts.get(index, 0) < TEAM_LIMIT
        plan.append(index if keep else None)
        if keep:
            counts[index] = counts.get(index, 0) + 1
    for i, index in enumerate(plan):
        if index is None:
            index = 0
            while index == AI_TEAM or counts.get(index, 0) >= TEAM_LIMIT:
                index += 1
            plan[i] = index
            counts[index] = counts.get(index, 0) + 1
    return plan


def team_sizes(indices):
    sizes = {}
    for index in indices:
        key = 'none' if index is None else str(index)
        sizes[key] = sizes.get(key, 0) + 1
    return dict(sorted(sizes.items()))


def team_index(pri):
    team = pri.Team
    return None if team is None or team.TeamIndex < 0 or team.TeamIndex == NO_TEAM else team.TeamIndex


def is_player(controller):
    """UnrealScript IsA('PlayerController') called from Python returned False for the host's
    WillowPlayerController, so compare classes. Engine classes are never unloaded: caching is safe."""
    global _player_class
    if _player_class is None:
        _player_class = unrealsdk.find_class('PlayerController')
    return controller is not None and controller.Class._inherits(_player_class)


def player_pris(game):
    """Human players as the HUD counts them (GRI.PRIArray, which holds no inactive PRIs), without spectators.

    TeamInfo.Size is not used: GameInfo.Logout does not remove a leaving player from their team.
    """
    return [p for p in game.GameReplicationInfo.PRIArray
            if p is not None and not p.bOnlySpectator and is_player(p.Owner)]


def ensure_team(game, index):
    """InitializeTeams creates teams 0 and 1; higher teams are created on demand, and on seamless
    travel by initialize_teams. Returns the team object for the index, if any."""
    if index > AI_TEAM and (len(game.Teams) <= index or game.Teams[index] is None):
        game.CreateTeam(index, f'Squad {index}')
    return game.Teams[index] if index < len(game.Teams) else None


def needs_move(game, pri, index):
    """Also true for the right index on a stale team object: seamless travel carries squad teams
    over, and the new GameInfo lists them only if initialize_teams created them."""
    if index is None:
        return pri.Team is not None
    return team_index(pri) != index or pri.Team != (game.Teams[index] if index < len(game.Teams) else None)


def apply_teams(pc):
    """Move players to the teams plan_teams chooses. Players leave teams before others join, and
    nobody joins a team that already holds TEAM_LIMIT players, so no HUD sees more than three
    allies even between two moves. Remembers the squad teams in use for initialize_teams."""
    global _teams_status, _last_teams_status, _squad_teams
    game = pc.WorldInfo.Game
    if game is None:
        return
    mode = team_mode.value
    try:
        pris = player_pris(game)
        current = [team_index(p) for p in pris]
        plan = plan_teams(current, mode)
        _squad_teams = {i for i in current + plan if i is not None and i > AI_TEAM}
        moves = [(p, i) for p, i in zip(pris, plan) if needs_move(game, p, i)]
        moves.sort(key=lambda move: move[1] is not None)
        for pri, index in moves:
            if index is not None:
                if sum(team_index(q) == index for q in pris if q is not pri) >= TEAM_LIMIT:
                    continue  # retried on the next pass, after the others have left
                ensure_team(game, index)
            game.ChangeTeam(pri.Owner, NO_TEAM if index is None else index, False)
        status = dict(mode=mode, sizes=team_sizes([team_index(p) for p in pris]))
    except Exception as exc:
        status = dict(mode=mode, error=str(exc))
    _teams_status = status
    if status != _last_teams_status:
        logging.info(f'Unlimited COOP teams: {status}')
        _last_teams_status = status


def plain(value):
    """A property value as plain Python: arrays (of enum values) as lists of ints."""
    return value if isinstance(value, (bool, int, float, str)) else [int(v) for v in value]


def vehicle_writes(current, stock, tweak, on):
    """Properties to write to one definition, and its stock values to keep afterwards (None: forget).

    current: its values now; stock: the values kept when the option was turned on, if any. While
    the option is on the tweak is written; once it is off the stock values are written back.
    """
    if on:
        return {p: v for p, v in tweak.items() if current[p] != v}, current if stock is None else stock
    return {p: v for p, v in (stock or {}).items() if current[p] != v}, None


def apply_definition(obj, cls, on):
    """Write the tweak (on) or the kept stock values (off) to one definition and read it back.
    Returns its stock values while it is tweaked, None once they are restored."""
    tweak = VEHICLE_TWEAKS[cls][1]
    kept = _vehicle_stock.setdefault(cls, {})
    path = obj._path_name()
    writes, stock = vehicle_writes({p: plain(getattr(obj, p)) for p in tweak}, kept.get(path), tweak, on)
    for prop, value in writes.items():
        setattr(obj, prop, value)
        if plain(getattr(obj, prop)) != value:
            raise RuntimeError(f'Readback differs: {path}.{prop}')
    if stock is None:
        kept.pop(path, None)
    else:
        kept[path] = stock
    return stock


def apply_vehicles(_pc, cls):
    """Apply one class of VEHICLE_TWEAKS to every loaded definition (a full GObjects scan).

    Stations load their definitions with the map, DLC ones with DLC maps, so this runs in the
    full passes after a map change; chassis load with each vehicle, see vehicle_spawned. Stock
    values are kept by object path; once the option is off they are restored and forgotten: a
    definition that is not loaded now loads again with stock values.
    """
    option, tweak = VEHICLE_TWEAKS[cls]
    on = bool(option.value)
    status = dict(on=on, loaded=0, changed=0)
    try:
        for obj in unrealsdk.find_all(cls):
            if obj.Name.startswith('Default__'):
                continue
            stock = apply_definition(obj, cls, on)
            status['loaded'] += 1
            status['changed'] += stock is not None and stock != tweak
        if not on:
            _vehicle_stock.pop(cls, None)
    except Exception as exc:
        status['error'] = str(exc)
    if status != _vehicles_status.get(cls):
        logging.info(f'Unlimited COOP vehicles: {cls} {status}')
    _vehicles_status[cls] = status


def say(text):
    """A message on the local HUD, and in the SDK log."""
    logging.info(f'Unlimited COOP reload: {text}')
    try:
        show_hud_message('Unlimited COOP', text, 6.0)
    except Exception as exc:
        logging.warning(f'Unlimited COOP: HUD message not shown: {exc}')


def map_name(pc):
    return str(pc.WorldInfo.GetMapName(False)).lower()


def level_of(station):
    level = str(station.GetStationLevelName()).lower()
    return MAP_ALIASES.get(level, level)


def ready(controller):
    """A player that travel can take along: in the game with a living pawn, not joining or saving.
    The game's CheckMapChangeConditions also checks this, but tells every player who is not."""
    pawn = controller.Pawn
    return (pawn is not None and pawn.IsAliveAndWell() and not controller.bIsInHolding
            and str(controller.GetStateName()) != 'PlayerLobby' and not controller.PlayerReplicationInfo.bIsSaving)


def arrived(pc, state):
    """The host's travel is done: the map change is committed and the loading screen is gone. The map name
    changes as soon as travel starts, and pawns are kept and moved."""
    return state['commits'] > 0 and pc.Pawn is not None and not pc.IsLoadingMoviePlaying()


def loaded(pc, controller, state, there, now):
    """Whether a player has the map `there` loaded: the host once arrived, a client once it reports the map
    visible, or RELOAD_GRACE after the host if the hook has seen no report at all."""
    if controller == pc:
        return True
    shown = state['visible'].get(controller._get_address())
    if shown is not None:
        return there in shown
    return not state['visible'] and now >= state['arrived'] + RELOAD_GRACE


def pick_hop(pc, home):
    """A fast travel station of another map that the host has discovered, in the main game (every player
    has it) and not closed by a mission objective. Sanctuary is left out: its station names Sanctuary_P,
    which the game may replace with the map the host is in."""
    lookup = unrealsdk.find_class('WillowGlobals').ClassDefaultObject.GetWillowGlobals().GetFastTravelStationsLookup()
    avoid = {map_name(pc), level_of(home)}
    for name in pc.ActivatedTeleportersList:
        station = lookup.FindFastTravelStationLookupObject(name)
        if (station is not None and station.DlcExpansion is None and not station.bSendOnly
                and station.InaccessibleObjective is None and level_of(station) not in avoid
                and not level_of(station).startswith('sanctuary')):
            return station
    return None


def population_master():
    return unrealsdk.find_class('GearboxGlobals').ClassDefaultObject.GetGearboxGlobals().GetPopulationMaster()


def population_definitions():
    """Loaded population definitions (a full GObjects scan per class)."""
    for cls in POPULATION_CLASSES:
        for obj in unrealsdk.find_all(cls, True):
            if not obj.Name.startswith('Default__'):
                yield obj


def connected_trackers():
    """bTotalResetOnLevelLoad of the population trackers of the loaded levels, by opportunity."""
    return {(str(t.OpportunityOutermostName), str(t.OpportunityName)): int(t.bTotalResetOnLevelLoad)
            for t in population_master().OpportunityList if t.LoadedOpportunity is not None}


def wipe_kismet(packages):
    """Drop the Kismet bank entries of the given level packages; returns how many."""
    dropped = 0
    for bank in unrealsdk.find_all('PersistentGameDataManager', True):
        if bank.Name.startswith('Default__'):
            continue
        entries = bank.SequencesWithPersistentData
        for i in reversed(range(len(entries))):
            if str(entries[i].LevelPackageName).lower() in packages:
                entries.pop(i)
                dropped += 1
    return dropped


def arm(state):
    """Set bTotalResetOnLevelLoad on every loaded population definition and on the class defaults, which
    definitions loading with the home map inherit; keep the values before by path."""
    stock = state['defs']
    for obj in population_definitions():
        stock.setdefault(obj._path_name(), bool(obj.bTotalResetOnLevelLoad))
        obj.bTotalResetOnLevelLoad = True
    for cls in POPULATION_CLASSES:
        default = unrealsdk.find_class(cls).ClassDefaultObject
        state['defaults'].setdefault(cls, bool(default.bTotalResetOnLevelLoad))
        default.bTotalResetOnLevelLoad = True
    state['armed'] = True


def disarm(state):
    """Put back the stock values: the class defaults, every loaded definition (its value before, or for one
    first loaded since, its game data), and the flag in the home map's trackers."""
    if not state.get('armed'):
        return
    state['armed'] = False
    for cls, value in state['defaults'].items():
        unrealsdk.find_class(cls).ClassDefaultObject.bTotalResetOnLevelLoad = value
    restored = 0
    for obj in population_definitions():
        path = obj._path_name()
        value = state['defs'].get(path, path in RESET_ON_LOAD)
        if bool(obj.bTotalResetOnLevelLoad) != value:
            obj.bTotalResetOnLevelLoad = value
            restored += 1
    for t in population_master().OpportunityList:
        value = state['trackers'].get((str(t.OpportunityOutermostName), str(t.OpportunityName)))
        if value is not None and int(t.bTotalResetOnLevelLoad) != value:
            t.bTotalResetOnLevelLoad = value
    logging.info(f'Unlimited COOP reload: stock values back, {restored} definitions restored')


def request_reload():
    """The option button. The reload starts once the host is back in the game with the menus closed."""
    global _reload
    if _reload is None:
        _reload = dict(stage='request', next=0.0, armed=False)


def reload_request(pc, state, now):
    if pc.IsPauseMenuOpen() or pc.PlayerReplicationInfo.bGFxMenuOpen:
        return None
    state['stage'] = 'done'
    game = pc.WorldInfo.Game
    if not is_host(pc) or game is None:
        return 'Only the host can reload the map.'
    home = pc.LastVisitedTeleporter
    if home is None or level_of(home) != map_name(pc):
        return 'Map reload: the game would bring you back to another map. Use a station of this map first.'
    hop = pick_hop(pc, home)
    if hop is None:
        return 'Map reload needs a fast travel station you have discovered in another main-game map.'
    if game.TravelCountdownInProcess() or not game.CheckMapChangeConditions():
        return 'Map reload: wait until travel is possible for everyone, then try again.'
    packages = {map_name(pc)} | {str(s.PackageName).lower() for s in pc.WorldInfo.StreamingLevels
                                 if s is not None and s.LoadedLevel is not None}
    state.update(stage='hop', home=home, hop=hop, home_map=map_name(pc), packages=packages, defs={}, defaults={},
                 trackers=connected_trackers(), until=now + RELOAD_WAIT, seen=0, commits=0, arrived=None, visible={})
    for obj in population_definitions():  # their stock values, before anything is changed
        state['defs'][obj._path_name()] = bool(obj.bTotalResetOnLevelLoad)
    game.TravelToStation(hop)
    return f'Reloading the map: to {hop.StationDisplayName} and back.'


def reload_hop(pc, state, now):
    """On the other map with everyone loaded and ready, the home map is unloaded: forget its Kismet entries,
    set the flag and go back. Two checks in a row, so the map has settled."""
    game = pc.WorldInfo.Game
    there = map_name(pc)
    if state['arrived'] is None and arrived(pc, state) and there not in (state['home_map'], *NOT_A_MAP):
        state['arrived'] = now
    everyone = state['arrived'] is not None and all(ready(p.Owner) and loaded(pc, p.Owner, state, there, now)
                                                    for p in player_pris(game))
    state['seen'] = state['seen'] + 1 if everyone else 0
    if state['seen'] < 2:
        if now > state['until']:
            state['stage'] = 'done'
            return 'Map reload stopped: not everyone loaded the other map in time. Nothing was reset; travel back.'
        return None
    dropped = wipe_kismet(state['packages'])
    arm(state)
    logging.info(f"Unlimited COOP reload: {dropped} Kismet entries of {sorted(state['packages'])} dropped,"
                 f" back after {now - state['arrived']:.1f} s on {there}; clients reported {len(state['visible'])}")
    state.update(stage='home', until=now + RELOAD_WAIT, arrived=None, commits=0)
    game.TravelToStation(state['home'])
    return None


def reload_home(pc, state, now):
    """Back home: once its populations are connected again, put the stock values back."""
    if map_name(pc) != state['home_map'] or not arrived(pc, state):
        if now > state['until']:
            state['stage'] = 'done'
            return 'Map reload stopped: the map did not load in time. Stock values are back.'
        return None
    if state['arrived'] is None:
        state['arrived'] = now
    if now < state['arrived'] + RELOAD_SETTLE and not set(state['trackers']) <= set(connected_trackers()):
        return None
    state['stage'] = 'done'
    return 'Map reloaded.'


RELOAD_STAGES = dict(request=reload_request, hop=reload_hop, home=reload_home)


def reload_step(pc, now):
    """One step of the map reload. It ends with the stock values back, also on an error or in the menu."""
    global _reload
    state = _reload
    state['next'] = now + RELOAD_STEP
    try:
        if map_name(pc) == 'menumap':
            state['stage'] = 'done'
            message = None
        else:
            message = RELOAD_STAGES[state['stage']](pc, state, now)
    except Exception as exc:
        state['stage'] = 'done'
        message = f'Map reload failed: {exc}'
    if state['stage'] == 'done':
        _reload = None
        try:
            disarm(state)
        except Exception as exc:
            logging.error(f'Unlimited COOP: stock population values not restored: {exc}')
    if message:
        say(message)


def pass_steps(full, vehicles=False, host=True):
    """A full pass covers every target; otherwise only targets not yet read back with the values wanted
    now (cheap object lookups), so an option change applies in the next pass. Every pass checks the
    player counts and teams: a few PRIs, and a join or leave must not wait for a full pass. Balance
    tables are looked up by name, only while they are continued or wait to be restored.

    Vehicle definitions are scanned in full passes and after a vehicle option change, only while
    their option is on or stock values wait to be restored. A client runs nothing else.
    """
    steps = [(apply_vehicles, cls) for cls, (option, _) in VEHICLE_TWEAKS.items()
             if (full or vehicles) and (option.value or _vehicle_stock.get(cls))]
    if not host:
        return steps
    targets = [t for t, indices in TARGETS.items() if full or not all(map(settled, indices))]
    tables = [(apply_table, p) for p in TABLES if table_due(p, full)]
    balance = [(apply_globals,)] if full or _globals_status['status'] != 'read_back' else []
    return ([(apply_players,), (apply_teams,)] + balance + [(apply_target, t) for t in targets] + tables
            + steps + [(report,)])


def run_step(pc, step):
    step[0](pc, *step[1:])


def apply_patch():
    """Run a full pass at once (diagnostic scripts); the tick hook spreads passes over frames."""
    pc = controller()
    if pc is None:
        return
    for step in pass_steps(True, host=is_host(pc)):
        run_step(pc, step)


def start_pass(pc):
    """Queue the next pass. Full passes only follow triggers, at growing intervals; the rest are light.

    Triggers are map changes and player-count changes: a join or leave brings new instances and may
    switch the network block and the balance tables. A vehicle option change brings the vehicle
    steps into the next pass.
    """
    global _next_check, _next_full, _full_delay, _world, _players, _extra, _vehicle_options
    world = (pc.WorldInfo._path_name(), pc.WorldInfo._get_address(), pc.WorldInfo.GetMapName(True))
    game = pc.WorldInfo.Game
    players = None if game is None else player_count(game)
    if world != _world:
        _world = world
        invalidate()
    if players != _players:  # a join or leave brings new instances, the network block and balance tables
        _players = players
        _next_full, _full_delay = 0.0, CHECK_INTERVAL
    _extra = max((players or 0) - STOCK_PLAYERS, 0)
    now = time.monotonic()
    _next_check = now + CHECK_INTERVAL
    full = now >= _next_full
    if full:
        _next_full = now + _full_delay if _full_delay <= FOLLOW_UP_MAX else float('inf')
        _full_delay *= 2
    options = tuple(option.value for option, _ in VEHICLE_TWEAKS.values())
    vehicles, _vehicle_options = options != _vehicle_options, options
    _queue[:] = pass_steps(full, vehicles, is_host(pc))


@hook('WillowGame.WillowCoopGameInfo:PickTeam')
def pick_team(obj, args, _ret, _func):
    """Team of a joining player (Login passes no controller yet), as plan_teams would place them.

    The original patch returned Num here, 255 without a Team URL option: no team. Login turns
    the player into a spectator if joining the returned team fails, so a squad team is created
    first, and any error falls back to no team.
    """
    global _pick_calls
    if int(obj.WorldInfo.NetMode) == 3:
        return None
    _pick_calls += 1
    if args.C is not None and not is_player(args.C):
        return Block, args.Num
    try:
        index = plan_teams([team_index(p) for p in player_pris(obj)] + [None], team_mode.value)[-1]
        if index is not None:
            ensure_team(obj, index)
            if index > AI_TEAM:
                _squad_teams.add(index)
    except Exception as exc:
        logging.error(f'Unlimited COOP: team choice failed, joining without a team: {exc}')
        index = None
    return Block, NO_TEAM if index is None else index


@hook('WillowGame.WillowCoopGameInfo:InitializeTeams', Type.POST)
def initialize_teams(obj, _args, _ret, _func):
    """Create the squad teams in use before seamless travel in the new GameInfo.

    Fast travel keeps the GameInfo and its teams: maps stream into the persistent Loader world.
    Loading a game from the main menu is seamless travel to a new Loader world: PostSeamlessTravel
    of the new GameInfo calls InitializeTeams (teams 0 and 1), then HandleSeamlessTravelPlayer
    moves each player to the new GameInfo's team with their index, if the index is below
    Teams.Length. With the squad teams created here, the game moves squads at once and with right
    team sizes, instead of leaving them on stale teams until apply_teams. A missing team below the
    length would make the game drop its players from their teams, so there are no gaps.
    """
    if int(obj.WorldInfo.NetMode) == 3 or not _squad_teams:
        return
    try:
        for index in range(AI_TEAM + 1, max(_squad_teams) + 1):
            ensure_team(obj, index)
    except Exception as exc:
        logging.error(f'Unlimited COOP: squad teams not created before travel: {exc}')


@hook('WillowGame.WillowCoopGameInfo:PostLogin', Type.POST)
@hook('WillowGame.WillowCoopGameInfo:Logout', Type.POST)
@hook('WillowGame.WillowCoopGameInfo:HandleSeamlessTravelPlayer', Type.POST)
def players_changed(obj, _args, _ret, _func):
    """Set EffectiveNumPlayers right after the game sets it to NumPlayers.

    GameInfo does that in PostLogin, Logout and HandleSeamlessTravelPlayer. WillowCoopGameInfo
    overrides all three and calls them through super, so these POST hooks run after the whole chain.
    The network block and the balance tables follow in the next frames: passes restart at once.
    """
    if int(obj.WorldInfo.NetMode) == 3:
        return
    try:
        set_effective(obj)
    except Exception as exc:
        logging.error(f'Unlimited COOP: EffectiveNumPlayers not set: {exc}')
    invalidate()


@hook('WillowGame.WillowVehicle:PostBeginPlay', Type.POST)
def vehicle_spawned(obj, _args, _ret, _func):
    """Stand on vehicles for a new vehicle. Chassis definitions of player vehicles load with the
    vehicle (GD_Runner_Streaming and the like), usually long after the passes of a map change."""
    chassis = obj.ChassisDef
    if chassis is None or not VEHICLE_TWEAKS['ChassisDefinition'][0].value:
        return
    try:
        apply_definition(chassis, 'ChassisDefinition', True)
    except Exception as exc:
        logging.error(f'Unlimited COOP: Stand on vehicles not applied to {chassis._path_name()}: {exc}')


def invalidate(*_):
    """Restart full passes at once. Seamless travel fires several map hooks within seconds; passes write
    only values that differ, so unchanged objects are not written again."""
    global _next_check, _next_full, _full_delay
    _queue.clear()
    _next_check = _next_full = 0.0
    _full_delay = CHECK_INTERVAL


@hook('Engine.GameInfo:PostCommitMapChange', Type.POST)
@hook('WillowGame.WillowGameInfo:PostBeginPlay', Type.POST)
@hook('WillowGame.FrontendGFxMovie:Start', Type.POST)
def map_ready(*_):
    invalidate()
    if _reload is not None:
        _reload['commits'] = _reload.get('commits', 0) + 1


@hook('Engine.PlayerController:ServerUpdateLevelVisibility')
def level_visible(obj, args, _ret, _func):
    """A client reports a level it has made visible, on the host. During the map reload's first travel this
    tells when a client has the other map loaded."""
    if _reload is not None and _reload['stage'] == 'hop' and args.bIsVisible:
        _reload['visible'].setdefault(obj._get_address(), set()).add(str(args.PackageName).lower())


@hook('Engine.PlayerController:PlayerTick', Type.POST)
def tick(obj, _args, _ret, _func):
    # One step per frame: a whole pass in one frame stalled the game thread for ~100 ms every 2 s.
    now = time.monotonic()
    reloading = _reload is not None and now >= _reload['next']
    if not _queue and now < _next_check and not reloading:
        return
    pc = controller()
    if pc is None or obj != pc:
        return
    if reloading:
        reload_step(pc, now)
    if not _queue and now < _next_check:
        return
    if not _queue:
        start_pass(pc)
    if _queue:  # a client pass is empty while no vehicle option needs work
        run_step(pc, _queue.pop(0))


mod = build_mod(cls=RestartToDisable,
                options=[team_mode, stronger_enemies, enemy_strength, more_enemies, instant_travel,
                         stand_on_vehicles, any_vehicle_station, reload_map],
                hooks=[pick_team, initialize_teams, players_changed, vehicle_spawned, map_ready, level_visible,
                       tick],
                on_enable=invalidate)
