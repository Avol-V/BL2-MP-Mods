"""Offline checks that patch passes stay cheap per frame, are scheduled by triggers, and switch the
network block, the travel option and the player count."""
import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
FUNCTIONS = ('fail', 'apply_target', 'report', 'snapshot', 'pass_steps', 'run_step', 'apply_patch', 'start_pass',
             'invalidate', 'tick', 'is_host', 'player_count', 'set_effective', 'apply_players', 'players_changed',
             'group_on', 'typed', 'same', 'stock_of', 'settled', 'table_key', 'table_due')
CONSTANTS = ('TARGETS', 'CORE', 'CHECK_INTERVAL', 'FOLLOW_UP_MAX', 'VEHICLE_TWEAKS', 'STOCK_PLAYERS', 'LOBBY',
             'NETWORK', 'TRAVEL', 'STRONGER', 'MORE', 'NETWORK_STOCK')
chosen = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        node.decorator_list = []
        chosen.append(node)
    elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and (t.id in CONSTANTS or t.id.startswith('_')) for t in node.targets):
        chosen.append(node)
code = compile(ast.Module(body=chosen, type_ignores=[]), 'isolated_scheduling', 'exec')


class Obj:
    """A UObject with properties; writes are logged once it is built."""

    def __init__(self, path, writes, archetype=None, **props):
        self.__dict__.update(props, path=path, writes=writes, ObjectArchetype=archetype)

    def __setattr__(self, name, value):
        self.writes.append((self.path, name, value))
        super().__setattr__(name, value)

    def _path_name(self): return self.path
    def _get_address(self): return id(self)


class WorldInfo:
    NetMode = 2

    def __init__(self, game): self.Game = game
    def _path_name(self): return 'map.TheWorld:PersistentLevel.WorldInfo_0'
    def _get_address(self): return 1
    def GetMapName(self, _): return 'map'


class Controller:
    def __init__(self, game=None): self.WorldInfo = WorldInfo(game)


RECORDS = [dict(target='GameInfo', prop='MaxPlayers', value='0', group='lobby'),
           dict(target='GameInfo', prop='MaxPlayersAllowed', value='512', group='lobby'),
           dict(target='WillowCoopGameInfo', prop='TotalNetBandwidth', value='640000', group='network'),
           dict(target='GlobalsDefinition', prop='TravelDelay', value='0', group='travel')]
TABLES = {'GD_Balance.Table': 'stronger', 'GD_Balance.Formula': 'more'}


def load(records=RECORDS):
    ns = dict(json=json, RECORDS=records, TABLES=TABLES, __version__='test', SOURCE_SHA256='sha',
              logging=SimpleNamespace(info=lambda *_: None, error=lambda *_: None),
              stand_on_vehicles=SimpleNamespace(value=False), any_vehicle_station=SimpleNamespace(value=False),
              stronger_enemies=SimpleNamespace(value=True), enemy_strength=SimpleNamespace(value=100),
              more_enemies=SimpleNamespace(value=False), instant_travel=SimpleNamespace(value=False))
    exec(code, ns)
    return ns


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.ns = ns = load()
        self.clock = [100.0]
        self.writes = []
        self.resolved = []
        self.cdo = self.game_info('WillowGame.Default__WillowCoopGameInfo', players=0)
        self.game = self.game_info('Loader.TheWorld:PersistentLevel.WillowCoopGameInfo_0', self.cdo, players=1)
        self.speed_updates = []
        self.pc = Controller(self.game)
        self.objects = {'GameInfo': [self.cdo, self.game], 'WillowCoopGameInfo': [self.cdo, self.game]}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dest = Path(tmp.name) / 'unlimited_coop.runtime.json'

        def resolve(target):
            self.resolved.append(target)
            if target not in self.objects:
                raise ValueError("Couldn't find object " + target)
            return self.objects[target]

        def apply_globals(_pc):  # the rows themselves are covered by test_balance
            ns['_globals_status'] = dict(status='read_back')

        self.teams = []
        self.vehicles = []
        self.tables = []

        def apply_teams(pc):  # team assignment itself is covered by test_teams
            self.teams.append(pc)

        def apply_vehicles(_pc, cls):  # the vehicle step itself is covered by test_vehicles
            self.vehicles.append(cls)

        def apply_table(_pc, path):  # the tables themselves are covered by test_balance
            self.tables.append(path)
            extra, strength = ns['table_key'](TABLES[path])
            ns['_tables'][path] = dict(group=TABLES[path], status='read_back', above_four=extra, strength=strength)
            if extra:
                ns['_table_stock'][path] = {}
            else:
                ns['_table_stock'].pop(path, None)
        ns.update(time=SimpleNamespace(monotonic=lambda: self.clock[0]), resolve=resolve,
                  controller=lambda: self.pc, apply_globals=apply_globals, apply_teams=apply_teams,
                  apply_vehicles=apply_vehicles, apply_table=apply_table, SETTINGS_DIR=Path(tmp.name))

    def game_info(self, path, archetype=None, players=1, bandwidth=32000):
        game = Obj(path, self.writes, archetype, MaxPlayers=4, MaxPlayersAllowed=16, TotalNetBandwidth=bandwidth,
                   EffectiveNumPlayers=players, NumPlayers=players, WorldInfo=SimpleNamespace(NetMode=2))
        game.__dict__['UpdateNetSpeeds'] = lambda: self.speed_updates.append(path)
        return game

    def start(self, second):
        self.clock[0] = 100.0 + second
        self.ns['start_pass'](self.pc)
        steps = [s[1] if len(s) > 1 else s[0].__name__ for s in self.ns['_queue']]
        for step in list(self.ns['_queue']):
            self.ns['run_step'](self.pc, step)
        return steps

    def test_full_pass_resolves_each_target_once(self):
        self.ns['apply_patch']()
        self.assertEqual(self.resolved, ['GameInfo', 'WillowCoopGameInfo', 'GlobalsDefinition'])
        self.assertEqual(sorted(self.writes), sorted((o.path, p, v) for o in (self.cdo, self.game)
                                                     for p, v in (('MaxPlayers', 0), ('MaxPlayersAllowed', 512))))
        self.assertEqual([self.ns['_rows'][i]['status'] for i in range(4)], ['read_back'] * 3 + ['pending'])
        self.assertEqual(self.ns['_core']['WillowCoopGameInfo'][1]['NumPlayers'], 1)
        self.ns['apply_patch']()
        self.assertEqual(len(self.writes), 4, 'values already in place are not written again')

    def test_tick_runs_one_step_per_frame(self):
        tick = self.ns['tick']
        tick(self.pc, None, None, None)
        self.assertEqual(self.ns['_players_status']['EffectiveNumPlayers'], 1, 'the first step is the player count')
        tick(self.pc, None, None, None)
        self.assertEqual((self.resolved, self.teams), ([], [self.pc]), 'then teams')
        tick(self.pc, None, None, None)
        self.assertEqual((self.resolved, self.ns['_globals_status']), ([], dict(status='read_back')), 'then globals')
        for expected in (['GameInfo'], ['GameInfo', 'WillowCoopGameInfo'],
                         ['GameInfo', 'WillowCoopGameInfo', 'GlobalsDefinition']):
            tick(self.pc, None, None, None)
            self.assertEqual(self.resolved, expected)
        tick(self.pc, None, None, None)  # report
        self.assertTrue(self.dest.exists())
        self.assertEqual(self.ns['_queue'], [])
        self.clock[0] += 1.9
        tick(self.pc, None, None, None)
        self.assertEqual((len(self.resolved), self.ns['_queue']), (3, []), 'no work between passes')
        self.clock[0] += 0.1
        tick(Controller(self.game), None, None, None)
        self.assertEqual(self.ns['_queue'], [], 'a remote controller must not start or consume a pass')
        tick(self.pc, None, None, None)
        self.assertEqual(len(self.ns['_queue']), 6, 'second full pass, the player step done')

    def test_full_passes_only_follow_triggers(self):
        full = []
        for second in range(0, 600, 2):
            steps = self.start(second)
            if 'GameInfo' in steps:
                full.append(second)
            else:
                self.assertEqual(steps, ['apply_players', 'apply_teams', 'GlobalsDefinition', 'report'],
                                 'light pass: player count, teams and unsettled targets only')
        self.assertEqual(full, [0, 2, 6, 14, 30, 62], 'no periodic full passes without a trigger')

    def test_triggers_restart_full_passes(self):
        for second in (0, 2):
            self.start(second)
        self.assertNotIn('GameInfo', self.start(4))
        self.game.NumPlayers = 2
        self.assertIn('GameInfo', self.start(4), 'a join forces a full pass')
        self.assertNotIn('GameInfo', self.start(5), 'backoff restarts from 2 s after a join')
        self.clock[0] = 120.0
        self.ns['_queue'].append('stale')
        self.ns['invalidate']()
        self.assertEqual((self.ns['_queue'], self.ns['_next_check']), ([], 0.0))
        self.assertIn('GameInfo', self.start(20), 'a map change forces a full pass')

    def test_new_instances_are_written_only_where_they_differ(self):
        ns = self.ns
        for second in (0, 1, 3):  # several map hooks of one seamless travel
            self.clock[0] = 100.0 + second
            ns['invalidate']()
            ns['apply_patch']()
        self.assertEqual(len(self.writes), 4)
        stock = self.game_info('Loader.TheWorld:PersistentLevel.WillowCoopGameInfo_1', self.cdo)
        copied = self.game_info('Loader.TheWorld:PersistentLevel.WillowCoopGameInfo_2', self.cdo)
        copied.__dict__.update(MaxPlayers=0, MaxPlayersAllowed=512)
        self.objects['GameInfo'] = self.objects['WillowCoopGameInfo'] = [self.cdo, stock, copied]
        ns['invalidate']()
        ns['apply_patch']()
        self.assertEqual(self.writes[4:], [(stock.path, 'MaxPlayers', 0), (stock.path, 'MaxPlayersAllowed', 512)])

    def test_network_block_above_four_players(self):
        ns = self.ns
        self.start(0)
        self.assertEqual((self.cdo.TotalNetBandwidth, self.game.TotalNetBandwidth, self.speed_updates),
                         (32000, 32000, []), 'up to four players the network values are not touched')
        self.assertFalse(ns['_players_status']['network'])
        self.game.NumPlayers = 5
        self.start(1)
        self.assertEqual((self.cdo.TotalNetBandwidth, self.game.TotalNetBandwidth), (640000, 640000))
        self.assertEqual(self.speed_updates, [self.game.path], 'client net speeds follow at once')
        self.assertTrue(ns['_players_status']['network'])
        # A map load spawns a new GameInfo from the changed class default object.
        new = self.game_info('Loader.TheWorld:PersistentLevel.WillowCoopGameInfo_1', self.cdo, players=5,
                             bandwidth=640000)
        self.pc.WorldInfo.Game = new
        self.objects['GameInfo'] = self.objects['WillowCoopGameInfo'] = [self.cdo, new]
        ns['invalidate']()
        self.start(2)
        self.assertEqual([w for w in self.writes if w[1] == 'TotalNetBandwidth'],
                         [(self.cdo.path, 'TotalNetBandwidth', 640000), (self.game.path, 'TotalNetBandwidth', 640000)])
        new.NumPlayers = 4
        self.start(3)
        self.assertEqual((self.cdo.TotalNetBandwidth, new.TotalNetBandwidth), (32000, 32000),
                         'the new instance gets the stock value of its archetype')
        self.assertFalse(ns['_players_status']['network'])

    def test_traces_of_older_versions_get_stock_values(self):
        ns = self.ns
        # Up to 1.4.0 the console set saved the patch value to the user's ini: the game loads it.
        for game in (self.cdo, self.game):
            game.__dict__['TotalNetBandwidth'] = 640000
        self.start(0)
        self.assertEqual((self.cdo.TotalNetBandwidth, self.game.TotalNetBandwidth), (32000, 32000))
        self.game.NumPlayers = 5
        self.start(1)
        self.assertEqual(self.game.TotalNetBandwidth, 640000)
        self.game.NumPlayers = 4
        self.start(2)
        self.assertEqual((self.cdo.TotalNetBandwidth, self.game.TotalNetBandwidth), (32000, 32000))
        self.assertTrue(ns['_rows'][2]['status'] == 'read_back' and not ns['_rows'][2]['on'])

    def test_own_network_values_are_kept(self):
        for game in (self.cdo, self.game):
            game.__dict__['TotalNetBandwidth'] = 100000
        self.ns['apply_patch']()
        self.assertEqual([w for w in self.writes if w[1] == 'TotalNetBandwidth'], [])

    def test_travel_option_keeps_stock_values_per_object(self):
        ns = self.ns
        default = Obj('WillowGame.Default__GlobalsDefinition', self.writes, TravelDelay=3)
        globals_ = Obj('GD_Globals.General.Globals', self.writes, default, TravelDelay=5)
        self.objects['GlobalsDefinition'] = [default, globals_]
        self.start(0)
        self.assertEqual([w for w in self.writes if w[1] == 'TravelDelay'], [], 'option off: stock values')
        ns['instant_travel'].value = True
        self.assertIn('GlobalsDefinition', self.start(1), 'an option change applies in the next light pass')
        self.assertEqual((default.TravelDelay, globals_.TravelDelay), (0, 0))
        self.assertNotIn('GlobalsDefinition', self.start(1.5))
        ns['instant_travel'].value = False
        self.start(1.7)
        self.assertEqual((default.TravelDelay, globals_.TravelDelay), (3, 5))

    def test_players_hook_sets_effective_count_at_once(self):
        ns = self.ns
        self.start(0)
        for players, effective in ((6, 4), (5, 4), (3, 3), (1, 1)):
            self.game.NumPlayers = self.game.EffectiveNumPlayers = players  # what the game sets
            ns['_queue'].append('stale')
            ns['players_changed'](self.game, None, None, None)
            self.assertEqual(self.game.EffectiveNumPlayers, effective)
            self.assertEqual((ns['_queue'], ns['_next_check']), ([], 0.0), 'passes restart at once')
        self.game.WorldInfo = SimpleNamespace(NetMode=3)
        self.game.NumPlayers = self.game.EffectiveNumPlayers = 6
        ns['players_changed'](self.game, None, None, None)
        self.assertEqual(self.game.EffectiveNumPlayers, 6, 'nothing on a client')

    def test_passes_fix_a_missed_player_count(self):
        ns = self.ns
        self.start(0)
        self.game.NumPlayers = self.game.EffectiveNumPlayers = 7
        self.start(1)
        self.assertEqual((self.game.EffectiveNumPlayers, ns['_players_status']['fixed_by_pass']), (4, 1))
        ns['player_count'] = lambda _game: 5  # a probe testing five players alone
        self.game.NumPlayers = self.game.EffectiveNumPlayers = 1
        self.start(2)
        self.assertEqual((self.game.EffectiveNumPlayers, ns['_players_status']['counted']), (4, 5))
        self.assertTrue(ns['_players_status']['network'])

    def test_tables_only_above_four_players(self):
        ns = self.ns
        self.assertNotIn('GD_Balance.Table', self.start(0), 'up to four players tables are not even looked up')
        self.game.NumPlayers = 6
        steps = self.start(1)
        self.assertEqual(steps[-2:], ['GD_Balance.Table', 'report'], 'more enemies is off')
        self.assertNotIn('GD_Balance.Table', self.start(1.5), 'read back: not in light passes')
        ns['enemy_strength'].value = 150
        self.assertIn('GD_Balance.Table', self.start(1.7), 'a strength change applies in the next light pass')
        self.assertEqual(ns['_tables']['GD_Balance.Table']['strength'], 1.5)
        ns['more_enemies'].value = True
        self.assertEqual(self.start(1.9)[-2:], ['GD_Balance.Formula', 'report'])
        self.game.NumPlayers = 4
        self.assertEqual(self.start(2)[-3:], ['GD_Balance.Table', 'GD_Balance.Formula', 'report'],
                         'back to four: one step each restores the stock values')
        self.assertNotIn('GD_Balance.Table', self.start(4), 'restored: not looked up again')
        self.assertEqual(ns['_tables'], {}, 'nor reported')

    def test_vehicle_steps_follow_options(self):
        ns = self.ns
        self.assertNotIn('ChassisDefinition', self.start(0), 'options off: no scans, even in a full pass')
        ns['stand_on_vehicles'].value = True
        self.assertEqual(self.start(1), ['apply_players', 'apply_teams', 'GlobalsDefinition', 'ChassisDefinition',
                                         'report'], 'an option change brings its class into the next light pass')
        self.assertNotIn('ChassisDefinition', self.start(1.5), 'not again in light passes')
        self.assertIn('ChassisDefinition', self.start(2), 'full passes scan while the option is on')
        ns['stand_on_vehicles'].value = False
        ns['_vehicle_stock']['ChassisDefinition'] = {'GD.Chassis': dict(AllowPawnsToStandOnTopOfVehicle=False)}
        self.assertIn('ChassisDefinition', self.start(3), 'turned off: one step restores the stock values')
        ns['_vehicle_stock']['ChassisDefinition'].clear()
        self.assertNotIn('ChassisDefinition', self.start(6), 'nothing to restore: no scans')
        ns['any_vehicle_station'].value = True
        self.assertEqual(self.start(7)[-4:-1], ['VehicleSpawnStationGFxDefinition', 'VSSUIDefinition',
                                                'VehicleFamilyDefinition'])

    def test_client_runs_only_vehicle_steps(self):
        self.pc.WorldInfo.NetMode = 3
        self.pc.WorldInfo.Game = None
        tick = self.ns['tick']
        for _ in range(3):
            tick(self.pc, None, None, None)
        self.assertEqual((self.resolved, self.teams, self.vehicles, self.writes), ([], [], [], []))
        self.ns['any_vehicle_station'].value = True
        self.clock[0] += 2
        for _ in range(5):
            tick(self.pc, None, None, None)
        self.assertEqual(self.vehicles, ['VehicleSpawnStationGFxDefinition', 'VSSUIDefinition', 'VehicleFamilyDefinition'])
        self.assertEqual((self.resolved, self.teams, self.tables, self.writes), ([], [], [], []),
                         'no patch records, teams or tables on a client')
        self.assertFalse(self.dest.exists(), 'no diagnostics on a client')

    def test_snapshot_written_only_on_change(self):
        ns = self.ns
        ns['apply_patch']()
        self.assertTrue(self.dest.exists())
        self.dest.unlink()
        ns['apply_patch']()
        self.assertFalse(self.dest.exists(), 'unchanged diagnostics must not be rewritten')
        self.objects['GlobalsDefinition'] = [Obj('GD_Globals.General.Globals', self.writes, TravelDelay=5)]
        ns['apply_patch']()
        report = json.loads(self.dest.read_text())
        self.assertEqual([r['status'] for r in report['records']], ['read_back'] * 4)
        self.assertEqual(report['records'][3]['values'], ['5'])
        self.assertEqual(list(report['core']), ['WillowCoopGameInfo', 'WillowOnlineGameSettings'])
        self.assertEqual(report['players']['EffectiveNumPlayers'], 1)
        self.assertEqual(report['options'], dict(stronger_enemies=True, strength=100, more_enemies=False,
                                                 instant_travel=False))
        self.assertNotIn('hotfix_service', report)


if __name__ == '__main__': unittest.main()
