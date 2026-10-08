"""Offline checks of what the mod takes from cooppatch.txt: the file is unchanged, the mod applies its
lobby, network and travel records, and no hotfix."""
import ast
import hashlib
import re
import unittest
from pathlib import Path

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
CONSTANTS = ('HOTFIX', 'TYPED', 'SECTION', 'LOBBY', 'NETWORK', 'TRAVEL', 'GROUPS', 'SKIPPED', 'NETWORK_STOCK')
chosen = [n for n in tree.body if
          (isinstance(n, ast.FunctionDef) and n.name in ('parse_patch', 'select_records')) or
          (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in CONSTANTS for t in n.targets))]
ns = {'re': re}
exec(compile(ast.Module(body=chosen, type_ignores=[]), 'isolated_patch_records', 'exec'), ns)
patch = ns['parse_patch']((source/'cooppatch.txt').read_text())
records = ns['select_records'](patch)


def group(name):
    return [(r['target'], r['prop']) for r in records if r['group'] == name]


class PatchRecordTests(unittest.TestCase):
    def test_patch_is_unchanged(self):
        self.assertEqual(hashlib.sha256((source/'cooppatch.txt').read_bytes()).hexdigest(),
                         '804f7f740ee2c1d0c5ca6a1e9dec5cbce4c9a6d3c7cf09407ff1c3b56b9712da')
        self.assertEqual(len(patch), 39)
        self.assertEqual(sum(bool(r['hotfix']) for r in patch), 13)

    def test_records_know_their_section(self):
        sections = {}
        for record in patch:
            sections[record['section']] = sections.get(record['section'], 0) + 1
        self.assertEqual(sections, {'CORE - MORE PLAYERS': 5, 'NETWORK OPTIMIZATION': 21, 'ENEMY DAMAGE FIX': 5,
                                    'KILL SKILLS FIX': 1, 'XP AWARD FIX': 1, 'MISC': 5, 'INSTANT FAST TRAVEL': 1})

    def test_applied_records(self):
        self.assertEqual(group('lobby'), [('WillowOnlineGameSettings', 'NumPublicConnections'),
                                          ('GameInfo', 'MaxPlayers'), ('GameInfo', 'MaxPlayersAllowed')])
        self.assertEqual(len(group('network')), 20, 'the network section without AdjustedNetSpeed')
        self.assertEqual(group('travel'), [('GlobalsDefinition', 'TravelDelay')])
        self.assertEqual(len(records), 24)

    def test_no_hotfix_effective_num_players_or_net_speed(self):
        self.assertFalse([r for r in records if r['hotfix']])
        self.assertFalse({r['prop'] for r in records} & {'EffectiveNumPlayers', 'AdjustedNetSpeed'})
        self.assertNotIn('SparkServiceConfiguration', (source/'__init__.py').read_text(),
                         'no hotfix registration left')

    def test_network_config_has_stock_values(self):
        # Not config, so never saved to the user's ini: TimeoutTime, NetUpdateFrequency.
        # Not in the game's ini, stock unknown: bClampListenServerTickRate.
        props = {r['prop'].lower() for r in records if r['group'] == 'network'}
        self.assertEqual(props - set(ns['NETWORK_STOCK']),
                         {'timeouttime', 'netupdatefrequency', 'bclamplistenservertickrate'})
        self.assertEqual(set(ns['NETWORK_STOCK']) - props, set())

    def test_values_are_scalars(self):
        for record in records:
            if record['value'].lower() not in ('true', 'false'):
                float(record['value'])  # raises for structs and text

    def test_targets_group_every_record_once(self):
        node = next(n for n in tree.body if isinstance(n, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == 'TARGETS' for t in n.targets))
        scope = dict(RECORDS=records)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'isolated_targets', 'exec'), scope)
        targets = scope['TARGETS']
        self.assertEqual(sorted(i for indices in targets.values() for i in indices), list(range(len(records))))
        self.assertEqual(len(targets), 9)


if __name__ == '__main__': unittest.main()
