"""Offline checks that patch passes stay cheap per frame and are scheduled by triggers."""
import ast
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
FUNCTIONS = ('parse_patch', 'fail', 'apply_target', 'report', 'snapshot', 'apply_service', 'pass_steps',
             'run_step', 'apply_patch', 'start_pass', 'invalidate', 'tick')
CONSTANTS = ('HOTFIX', 'TYPED', 'TARGETS', 'CORE', 'CHECK_INTERVAL', 'FOLLOW_UP_MAX', 'INVALIDATE_BURST')
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
    def __init__(self, path, **props):
        self.path = path
        self.InternalIndex = len(path)
        self.__dict__.update(props)

    def _path_name(self): return self.path
    def _get_address(self): return id(self)


class WorldInfo:
    NetMode = 2

    def __init__(self): self.Game = SimpleNamespace(NumPlayers=1)
    def _path_name(self): return 'map.TheWorld:PersistentLevel.WorldInfo_0'
    def _get_address(self): return 1
    def GetMapName(self, _): return 'map'


class Controller:
    def __init__(self):
        self.WorldInfo = WorldInfo()
        self.commands = []

    def ConsoleCommand(self, command, _):
        self.commands.append(command)
        return ''


RECORDS = [dict(target='GameInfo', prop='MaxPlayers', value='4', hotfix=None),
           dict(target='GameInfo', prop='MaxPlayersAllowed', value='512', hotfix=None),
           dict(target='WillowCoopGameInfo', prop='TotalNetBandwidth', value='600000', hotfix=None),
           dict(target='GD_Late.Formula', prop='ConditionalInitialization', value='(A=1)', hotfix='K1')]


def load(records=RECORDS):
    ns = dict(re=re, json=json, RECORDS=records, __version__='test', SOURCE_SHA256='sha',
              logging=SimpleNamespace(info=lambda *_: None))
    exec(code, ns)
    ns['COMMANDS'] = [f"set {r['target']} {r['prop']} {r['value']}" for r in records]
    return ns


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.ns = ns = load()
        self.clock = [100.0]
        self.pc = Controller()
        self.resolved = []
        game = Obj('map.TheWorld:PersistentLevel.WillowCoopGameInfo_0', MaxPlayers=4, MaxPlayersAllowed=512,
                   TotalNetBandwidth=600000, EffectiveNumPlayers=4, NumPlayers=1)
        self.objects = {'GameInfo': [game], 'WillowCoopGameInfo': [game]}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dest = Path(tmp.name) / 'unlimited_coop.runtime.json'

        def resolve(target):
            self.resolved.append(target)
            if target not in self.objects:
                raise ValueError("Couldn't find object " + target)
            return self.objects[target]

        def register_hotfixes():
            ns['_service_status'] = dict(status='registered')
        ns.update(time=SimpleNamespace(monotonic=lambda: self.clock[0]), resolve=resolve,
                  controller=lambda: self.pc, register_hotfixes=register_hotfixes, SETTINGS_DIR=Path(tmp.name))

    def test_targets_group_every_record_once(self):
        records = load()['parse_patch']((source/'cooppatch.txt').read_text())
        targets = load(records)['TARGETS']
        self.assertEqual(sorted(i for indices in targets.values() for i in indices), list(range(len(records))))
        self.assertEqual(len(targets), 22)
        for target, indices in targets.items():
            self.assertTrue(all(records[i]['target'] == target for i in indices))

    def test_full_pass_resolves_each_target_once(self):
        self.ns['apply_patch']()
        self.assertEqual(self.resolved, ['GameInfo', 'WillowCoopGameInfo', 'GD_Late.Formula'])
        self.assertEqual(self.pc.commands, self.ns['COMMANDS'][:3])
        self.assertEqual([self.ns['_rows'][i]['status'] for i in range(4)], ['read_back'] * 3 + ['pending'])
        self.assertEqual(self.ns['_core']['WillowCoopGameInfo'][0]['NumPlayers'], 1)
        self.ns['apply_patch']()
        self.assertEqual(len(self.pc.commands), 3, 'unchanged instances must not be re-applied')

    def test_tick_runs_one_step_per_frame(self):
        tick = self.ns['tick']
        tick(self.pc, None, None, None)
        self.assertEqual(self.resolved, [], 'the first step is the hotfix service')
        for expected in (['GameInfo'], ['GameInfo', 'WillowCoopGameInfo'],
                         ['GameInfo', 'WillowCoopGameInfo', 'GD_Late.Formula']):
            tick(self.pc, None, None, None)
            self.assertEqual(self.resolved, expected)
        tick(self.pc, None, None, None)  # report
        self.assertTrue(self.dest.exists())
        self.assertEqual(self.ns['_queue'], [])
        self.clock[0] += 1.9
        tick(self.pc, None, None, None)
        self.assertEqual((len(self.resolved), self.ns['_queue']), (3, []), 'no work between passes')
        self.clock[0] += 0.1
        tick(Controller(), None, None, None)
        self.assertEqual(self.ns['_queue'], [], 'a remote controller must not start or consume a pass')
        tick(self.pc, None, None, None)
        self.assertEqual(len(self.ns['_queue']), 4, 'second full pass, service step done')

    def start(self, second):
        self.clock[0] = 100.0 + second
        self.ns['start_pass'](self.pc)
        steps = [s[1] if len(s) > 1 else s[0].__name__ for s in self.ns['_queue']]
        for step in list(self.ns['_queue']):
            self.ns['run_step'](self.pc, step)
        return steps

    def test_full_passes_only_follow_triggers(self):
        full = []
        for second in range(0, 600, 2):
            steps = self.start(second)
            if 'GameInfo' in steps:
                full.append(second)
            else:
                self.assertEqual(steps, ['GD_Late.Formula', 'report'], 'light pass: unsettled targets only')
        self.assertEqual(full, [0, 2, 6, 14, 30, 62], 'no periodic full passes without a trigger')

    def test_triggers_restart_full_passes(self):
        for second in (0, 2):
            self.start(second)
        self.assertNotIn('GameInfo', self.start(4))
        self.pc.WorldInfo.Game.NumPlayers = 2
        self.assertIn('GameInfo', self.start(4), 'a join forces a full pass')
        self.assertNotIn('GameInfo', self.start(5), 'backoff restarts from 2 s after a join')
        self.clock[0] = 120.0
        self.ns['_seen'][0] = 'old'
        self.ns['invalidate']()
        self.assertEqual((self.ns['_seen'], self.ns['_queue']), ({}, []))
        self.assertIn('GameInfo', self.start(20), 'a map change forces a full pass')

    def test_map_hook_burst_applies_once(self):
        ns = self.ns
        ns['invalidate']()
        ns['apply_patch']()
        self.assertEqual(len(self.pc.commands), 3)
        for second in (1, 3, 9):  # further hooks of the same seamless travel
            self.clock[0] = 100.0 + second
            ns['invalidate']()
            ns['apply_patch']()
        self.assertEqual(len(self.pc.commands), 3, 'unchanged objects are applied once per map change')
        game = Obj('map.TheWorld:PersistentLevel.WillowCoopGameInfo_1', MaxPlayers=4, MaxPlayersAllowed=512,
                   TotalNetBandwidth=600000, EffectiveNumPlayers=4, NumPlayers=1)
        self.objects['GameInfo'] = self.objects['WillowCoopGameInfo'] = [game]
        self.clock[0] = 110.0
        ns['invalidate']()
        ns['apply_patch']()
        self.assertEqual(len(self.pc.commands), 6, 'new instances are applied within a burst')
        self.clock[0] = 125.0
        ns['invalidate']()
        ns['apply_patch']()
        self.assertEqual(len(self.pc.commands), 9, 'a later map change re-applies everything')

    def test_snapshot_written_only_on_change(self):
        ns = self.ns
        ns['apply_patch']()
        self.assertTrue(self.dest.exists())
        self.dest.unlink()
        ns['apply_patch']()
        self.assertFalse(self.dest.exists(), 'unchanged diagnostics must not be rewritten')
        self.objects['GD_Late.Formula'] = [Obj('GD_Late.Formula', ConditionalInitialization='(A=1)')]
        ns['apply_patch']()
        report = json.loads(self.dest.read_text())
        self.assertEqual([r['status'] for r in report['records']], ['read_back'] * 4)
        self.assertEqual(list(report['core']), ['WillowCoopGameInfo', 'WillowOnlineGameSettings'])


if __name__ == '__main__': unittest.main()
