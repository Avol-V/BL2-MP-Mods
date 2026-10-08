"""Offline checks of the balance by player count: experience and kill skill rows, and the balance tables
continued above four players. Stock tables are written as in the game data (BLCMM object dumps), in a
short notation: N==4&Champ==0&PT==1->1.75 is a branch with three conditions and its value."""
import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
FUNCTIONS = ('same', 'player_rows', 'rows_of', 'same_rows', 'apply_globals', 'player_condition', 'table_values',
             'read_table', 'table_slot', 'table_key', 'table_due', 'apply_table')
CONSTANTS = ('GLOBALS', 'PLAYER_ROWS', 'GLOBAL_ROWS', 'NUMBER_OF_PLAYERS', 'EQUAL', 'AT_LEAST', 'STRONGER', 'MORE',
             'TABLES', 'TYPOS', 'CHECK_INTERVAL')
chosen = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        chosen.append(node)
    elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and (t.id in CONSTANTS or t.id.startswith('_')) for t in node.targets):
        chosen.append(node)
code = compile(ast.Module(body=chosen, type_ignores=[]), 'isolated_balance', 'exec')
PLAYERS = 'D_Attributes.GameProperties.NumberOfPlayers'
ATTRIBUTES = {'N': PLAYERS, 'PT': 'D_Attributes.Balance.PlayThroughCount',
              'Champ': 'D_Attributes.Targetable.Targetable_Is_Champion'}
OPERATORS = {'==': 0, '<': 2, '<=': 3, '>': 4, '>=': 5}
# (default value, linear formula as (offset, level scale), branches) of every table the mod continues.
STOCK = {
    'Enemy_HealthBoost_PerPlayerPerPlaythroughByChampion': (1.0, None, 'N==1&Champ==0&PT==1->1; N==2&Champ==0&PT==1->1.2; N==3&Champ==0&PT==1->1.45; N==4&Champ==0&PT==1->1.75; N==1&Champ==1&PT==1->1; N==2&Champ==1&PT==1->2; N==3&Champ==1&PT==1->3; N==4&Champ==1&PT==1->4; N==1&Champ==0&PT==2->1.5; N==2&Champ==0&PT==2->1.725; N==3&Champ==0&PT==2->2.175; N==4&Champ==0&PT==2->2.625; N==1&Champ==1&PT==2->2; N==2&Champ==1&PT==2->4; N==3&Champ==1&PT==2->6; N==4&Champ==1&PT==2->8'),
    'Enemy_Damage_PerPlayerPerPlaythroughByChampion': (0.0, None, 'N==1&Champ==0&PT==1->0.65; N==2&Champ==0&PT==1->0.9; N==3&Champ==0&PT==1->1.03; N==4&Champ==0&PT==1->1.22; N==1&Champ==1&PT==1->0.74; N==2&Champ==1&PT==1->1; N==3&Champ==1&PT==1->1.13; N==4&Champ==1&PT==1->1.32; N==1&Champ==0&PT==2->1.05; N==2&Champ==0&PT==2->1.15; N==3&Champ==0&PT==2->1.35; N==4&Champ==0&PT==2->1.45; N==1&Champ==1&PT==2->1.3; N==2&Champ==1&PT==2->1.55; N==3&Champ==1&PT==2->1.8; N==4&Champ==1&PT==2->2.05'),
    'Init_EnemyGunDamage': (0.0, None, 'N<=1->0.8; N==2->0.95; N==3->1.15; N>=4->1.4'),
    'Init_EnemyShield_AdditionalShieldCapacityPerPlayer': (1.0, None, 'N==1->1; N==2->1.1; N==3->1.3; N==6->1.6'),
    'Init_EnemyVehicleHealthBoost_PerPlayerAndPlaythrough': (1.0, None, 'N==1&Champ==0&PT==1->1; N==2&Champ==0&PT==1->1.06; N==3&Champ==0&PT==1->1.12; N==4&Champ==0&PT==1->1.2; N==2&Champ==0&PT==2->1.06; N==3&Champ==0&PT==2->1.12; N==4&Champ==0&PT==2->1.2; N==4&Champ==0&PT==2->1.26; N==1&Champ==1&PT==1->1.3; N==2&Champ==1&PT==1->1.37; N==3&Champ==1&PT==1->1.44; N==4&Champ==1&PT==1->1.54; N==2&Champ==1&PT==2->1.37; N==3&Champ==1&PT==2->1.44; N==4&Champ==1&PT==2->1.54; N==4&Champ==1&PT==2->1.61'),
    'Enemy_MajorUpgrade_PerPlayer': (0.0, None, 'N<=1&PT==1->1; N==2&PT==1->1.5; N==3&PT==1->2; N>=4&PT==1->2.5; N<=1&PT==2->1.5; N==2&PT==2->2; N==3&PT==2->2.25; N>=4&PT==2->2.5'),
    'Enemy_Playthrough2OnlyBadass': (0.0, None, 'PT==1->0; N<=1&PT==2->2; N==2&PT==2->4; N==3&PT==2->5; N>=4&PT==2->6'),
    'Bosses_PerPlayers': (0.0, None, 'N==1->1; N==2->1; N==3->2; N>=4->3; N<=1&PT==2->2; N==2&PT==2->3; N==3&PT==2->4; N>=4&PT==2->6'),
    'WitchDoctors_PerPlayers': (0.0, None, 'N==1->1; N==2->1; N==3->2; N>=4->3; N<=1&PT==2->2; N==2&PT==2->3; N==3&PT==2->3; N>=4&PT==2->4'),
    'VDayWedding_BadassAdds_PerPlayer': (0.0, None, 'N<=1&PT==1->0.5; N==2&PT==1->0.75; N==3&PT==1->1; N>=4&PT==1->1.25; N<=1&PT==2->0.75; N==2&PT==2->1; N==3&PT==2->1.25; N>=4&PT==2->1.5; N<=1&PT>2->0.4; N==2&PT>2->0.6; N==3&PT>2->0.8; N>=4&PT>2->1'),
    'Formula_Add2In2PlayerAnd3In4Player': (0.0, None, 'N==2->2; N==3->2; N==4->3'),
    'Formula_AddOneIn2PlayerAndTwoIn4Player': (0.0, None, 'N==2->1; N==3->1; N==4->2'),
    'Formula_Add1PerAdditionalPlayer': (0.0, (-1.0, 1.0), ''),
    'Formula_ScaleBy25PercentPerAdditionalPlayer': (0.0, (0.75, 0.25), ''),
    'Constructor_EnemySpawned': (0.0, None, 'N==1&PT==1->2; N==2&PT==1->3; N==3&PT==1->4; N>=4&PT==1->5; N<=1&PT==2->3; N==2&PT==2->4; N==3&PT==2->5; N>=4&PT==2->6'),
    'Constructor_TotalEnemySpawned': (0.0, None, 'N==1&PT==1->6; N==2&PT==1->7; N==3&PT==1->8; N>=4&PT==1->10; N<=1&PT==2->8; N==2&PT==2->9; N==3&PT==2->10; N>=4&PT==2->12'),
    'FireMage_EnemySpawned': (0.0, None, 'N==1&PT==1->3; N==2&PT==1->4; N==3&PT==1->5; N>=4&PT==1->6; N<=1&PT==2->4; N==2&PT==2->5; N==3&PT==2->6; N>=4&PT==2->6'),
    'Necro_EnemySpawned': (0.0, None, 'N==1&PT==1->5; N==2&PT==1->5; N==3&PT==1->5; N>=4&PT==1->6; N<=1&PT==2->5; N==2&PT==2->5; N==3&PT==2->6; N>=4&PT==2->6'),
    'CrawmeraxMission_EnemySpawned': (0.0, None, 'N==1&PT==1->8; N==2&PT==1->10; N==3&PT==1->12; N>=4&PT==1->16; N<=1&PT==2->8; N==2&PT==2->10; N==3&PT==2->12; N>=4&PT==2->16; N==1&PT>2->6; N==2&PT>2->8; N==2&PT>2->10; N==2&PT>2->12'),
    'CrawmeraxMission_EnemyCrabsSpawned': (0.0, None, 'N==1&PT==1->8; N==2&PT==1->10; N==3&PT==1->12; N>=4&PT==1->16; N<=1&PT==2->8; N==2&PT==2->10; N==3&PT==2->12; N>=4&PT==2->16; N==1&PT>2->6; N==2&PT>2->8; N==2&PT>2->10; N==2&PT>2->12'),
    'CrawmeraxMission_EnemyFireBugsSpawned': (0.0, None, 'N==1&PT>=1->3; N==2&PT>=1->4; N==3&PT>=1->6; N>=4&PT>=1->8'),
}


def stock(name):
    """A stock table as read_table returns it."""
    default, formula, text = STOCK[name]
    rows = []
    for item in filter(None, text.split('; ')):
        conditions, value = item.split('->')
        parsed = []
        for condition in filter(None, conditions.split('&')):
            attribute, operator, constant = re.fullmatch(r'(\w+)(==|<=|>=|<|>)([\d.]+)', condition).groups()
            parsed.append((ATTRIBUTES[attribute], OPERATORS[operator], float(constant)))
        rows.append((float(value), tuple(parsed)))
    return dict(rows=rows, default=default, formula=formula)


class Attribute:
    def __init__(self, path): self.path = path
    def _path_name(self): return self.path


def value_data(value, scale=1.0, attribute=None):
    return SimpleNamespace(BaseValueConstant=value, BaseValueAttribute=attribute, InitializationDefinition=None,
                           BaseValueScaleConstant=scale)


def table_object(name):
    """An AttributeInitializationDefinition with the stock data, structs by reference as in the SDK."""
    data = stock(name)
    branches = [SimpleNamespace(BaseValueIfTrue=value_data(value), Expressions=[
        SimpleNamespace(AttributeOperand1=Attribute(a), ComparisonOperator=o, AttributeOperand2=None, ConstantOperand2=c)
        for a, o, c in conditions]) for value, conditions in data['rows']]
    offset, scale = data['formula'] or (0.0, 1.0)
    formula = SimpleNamespace(bEnabled=bool(data['formula']), Multiplier=value_data(1.0), Power=value_data(1.0),
                              Level=value_data(0.0, scale, Attribute(PLAYERS) if data['formula'] else None),
                              Offset=value_data(offset))
    return SimpleNamespace(ConditionalInitialization=SimpleNamespace(
        bEnabled=bool(branches), ConditionalExpressionList=branches, DefaultBaseValue=value_data(data['default'])),
        ValueFormula=formula)


def path(name):
    return next(p for p in load()['TABLES'] if p.rsplit('.', 1)[-1] == name)


def load(objects=None):
    ns = dict(stronger_enemies=SimpleNamespace(value=True), enemy_strength=SimpleNamespace(value=100),
              more_enemies=SimpleNamespace(value=False), logged=[])
    ns['logging'] = SimpleNamespace(info=ns['logged'].append)

    def find_object(_cls, name):
        if objects is None or name not in objects:
            raise ValueError(f"Couldn't find object '{name}'")
        return objects[name]
    ns['unrealsdk'] = SimpleNamespace(find_object=find_object, make_struct=lambda _name, **fields: SimpleNamespace(**fields))
    exec(code, ns)
    return ns


ns = load()


def values(name, extra, strength=1.0):
    table = stock(name)
    return ns['table_values'](table, extra, strength, ns['TYPOS'].get(path(name)))


class TableValueTests(unittest.TestCase):
    def assertValues(self, actual, expected):
        self.assertEqual(set(actual), set(expected))
        for slot, value in expected.items():
            self.assertAlmostEqual(actual[slot], value, places=5, msg=slot)

    def test_fixtures_cover_every_table(self):
        self.assertEqual({p.rsplit('.', 1)[-1] for p in ns['TABLES']}, set(STOCK))

    def test_every_table_changes_above_four_and_restores_at_four(self):
        for name in STOCK:
            table = stock(name)
            self.assertNotEqual(values(name, 1), values(name, 0), name)
            for slot, value in values(name, 0).items():
                if slot[0] == 'value':
                    self.assertEqual(value, table['rows'][slot[1]][0], name)

    def test_strength_zero_keeps_what_four_players_get(self):
        for name in STOCK:
            table, kept = stock(name), values(name, 3, 0.0)
            for slot, value in kept.items():
                if slot[0] == 'value':
                    typo = any(s[:2] == ('operand', slot[1]) for s in kept)
                    self.assertAlmostEqual(value, table['default'] if typo else table['rows'][slot[1]][0], places=5,
                                           msg=name)
                elif slot[0] == 'offset':
                    self.assertEqual(value, table['formula'][0], name)

    def test_enemy_health_and_damage(self):
        for extra, normal, champion, normal2, champion2 in ((1, 2.05, 5, 3.075, 10), (2, 2.35, 6, 3.525, 12),
                                                            (4, 2.95, 8, 4.425, 16)):
            self.assertValues(values('Enemy_HealthBoost_PerPlayerPerPlaythroughByChampion', extra),
                              {('value', 3): normal, ('value', 7): champion, ('value', 11): normal2,
                               ('value', 15): champion2})
        self.assertValues(values('Enemy_Damage_PerPlayerPerPlaythroughByChampion', 2),
                          {('value', 3): 1.6, ('value', 7): 1.7, ('value', 11): 1.65, ('value', 15): 2.55})
        self.assertValues(values('Init_EnemyGunDamage', 4), {('value', 3): 2.4})

    def test_strength_scales_the_step(self):
        for strength, value in ((0.0, 1.75), (0.5, 1.9), (1.0, 2.05), (2.0, 2.35)):
            self.assertAlmostEqual(values('Enemy_HealthBoost_PerPlayerPerPlaythroughByChampion', 1, strength)[('value', 3)],
                                   value, places=5)

    def test_shield_typo_starts_from_the_default(self):
        name = 'Init_EnemyShield_AdditionalShieldCapacityPerPlayer'
        self.assertEqual(values(name, 0), {('operand', 3, 0): 6.0, ('value', 3): 1.6}, 'stock: "== 6" -> 1.6')
        for extra, value in ((1, 1.3), (2, 1.6), (4, 2.2)):
            self.assertValues(values(name, extra), {('operand', 3, 0): 4.0, ('value', 3): value})
        self.assertValues(values(name, 1, 0.0), {('operand', 3, 0): 4.0, ('value', 3): 1.0})

    def test_repeated_branches_are_left_alone(self):
        self.assertValues(values('Init_EnemyVehicleHealthBoost_PerPlayerAndPlaythrough', 1),
                          {('value', 3): 1.28, ('value', 6): 1.28, ('value', 11): 1.64, ('value', 14): 1.64})

    def test_branches_without_a_three_player_branch_are_left_alone(self):
        self.assertValues(values('Enemy_Playthrough2OnlyBadass', 2), {('value', 4): 8})
        self.assertValues(values('CrawmeraxMission_EnemyCrabsSpawned', 1), {('value', 3): 20, ('value', 7): 20})

    def test_badass_weights(self):
        self.assertValues(values('Enemy_MajorUpgrade_PerPlayer', 1), {('value', 3): 3.0, ('value', 7): 2.75})
        self.assertValues(values('Bosses_PerPlayers', 2), {('value', 3): 5, ('value', 7): 10})

    def test_more_enemies(self):
        for extra, one, two in ((1, 3, 4), (2, 4, 5)):
            self.assertValues(values('Formula_AddOneIn2PlayerAndTwoIn4Player', extra), {('value', 2): one})
            self.assertValues(values('Formula_Add2In2PlayerAnd3In4Player', extra), {('value', 2): two})
        self.assertValues(values('Necro_EnemySpawned', 1), {('value', 3): 7, ('value', 7): 6})

    def test_linear_formulas_move_their_offset(self):
        self.assertEqual(values('Formula_Add1PerAdditionalPlayer', 0), {('offset',): -1.0})
        self.assertEqual(values('Formula_Add1PerAdditionalPlayer', 4), {('offset',): 3.0}, '8 players: N - 1 = 7')
        self.assertEqual(values('Formula_ScaleBy25PercentPerAdditionalPlayer', 1), {('offset',): 1.0})


class ApplyTableTests(unittest.TestCase):
    def setUp(self):
        self.name = 'Enemy_HealthBoost_PerPlayerPerPlaythroughByChampion'
        self.path = path(self.name)
        self.obj = table_object(self.name)
        self.ns = load({self.path: self.obj})

    def branch(self, index):
        return self.obj.ConditionalInitialization.ConditionalExpressionList[index].BaseValueIfTrue.BaseValueConstant

    def test_read_table_returns_the_stock_data(self):
        for name in STOCK:
            self.assertEqual(self.ns['read_table'](table_object(name)), stock(name), name)

    def test_writes_reads_back_and_restores(self):
        ns = self.ns
        ns['_extra'] = 2
        ns['apply_table'](None, self.path)
        self.assertEqual([round(self.branch(i), 4) for i in (2, 3, 7)], [1.45, 2.35, 6])
        status = ns['_tables'][self.path]
        self.assertEqual((status['status'], status['changed'], status['above_four']), ('read_back', 4, 2))
        ns['apply_table'](None, self.path)
        self.assertEqual(ns['_tables'][self.path]['changed'], 0, 'written once')
        self.assertFalse(ns['table_due'](self.path, False))
        ns['enemy_strength'].value = 50
        self.assertTrue(ns['table_due'](self.path, False), 'a strength change')
        ns['_extra'] = 0
        self.assertTrue(ns['table_due'](self.path, False), 'stock values wait to be restored')
        ns['apply_table'](None, self.path)
        self.assertEqual([self.branch(i) for i in (3, 7, 11, 15)], [1.75, 4, 2.625, 8])
        self.assertNotIn(self.path, ns['_table_stock'], 'restored: forgotten')
        self.assertFalse(ns['table_due'](self.path, True), 'not looked up again, even in full passes')

    def test_stock_is_kept_from_the_first_edit(self):
        ns = self.ns
        ns['_extra'] = 1
        ns['apply_table'](None, self.path)
        reloaded = table_object(self.name)  # a map change reloads the table with stock values
        ns['unrealsdk'].find_object = lambda _cls, _name: reloaded
        ns['_extra'] = 3
        ns['apply_table'](None, self.path)
        self.assertAlmostEqual(reloaded.ConditionalInitialization.ConditionalExpressionList[3].BaseValueIfTrue
                               .BaseValueConstant, 2.65, places=5)

    def test_pending_until_loaded(self):
        ns = load({})
        ns['_extra'] = 1
        ns['apply_table'](None, self.path)
        self.assertEqual(ns['_tables'][self.path]['status'], 'pending')
        self.assertTrue(ns['table_due'](self.path, False), 'retried in light passes')
        ns['_extra'] = 0
        ns['apply_table'](None, self.path)
        self.assertFalse(ns['table_due'](self.path, True), 'not loaded at four: it loads with stock values')

    def test_shield_operand_is_written(self):
        name = 'Init_EnemyShield_AdditionalShieldCapacityPerPlayer'
        obj = table_object(name)
        ns = load({path(name): obj})
        ns['_extra'] = 1
        ns['apply_table'](None, path(name))
        branch = obj.ConditionalInitialization.ConditionalExpressionList[3]
        self.assertEqual((branch.Expressions[0].ConstantOperand2, round(branch.BaseValueIfTrue.BaseValueConstant, 4)),
                         (4.0, 1.3))
        ns['_extra'] = 0
        ns['apply_table'](None, path(name))
        self.assertEqual((branch.Expressions[0].ConstantOperand2, round(branch.BaseValueIfTrue.BaseValueConstant, 4)),
                         (6.0, 1.6))

    def test_table_key_follows_options(self):
        ns = self.ns
        self.assertEqual(ns['table_key']('stronger'), (0, 0.0))
        ns['_extra'] = 2
        self.assertEqual((ns['table_key']('stronger'), ns['table_key']('more')), ((2, 1.0), (0, 0.0)))
        ns['enemy_strength'].value = 75
        ns['more_enemies'].value = True
        self.assertEqual((ns['table_key']('stronger'), ns['table_key']('more')), ((2, 0.75), (2, 1.0)))
        ns['stronger_enemies'].value = False
        self.assertEqual(ns['table_key']('stronger'), (0, 0.0))


class GlobalsTests(unittest.TestCase):
    def rows(self, cls, players, *values):
        return [SimpleNamespace(Players=p, **dict(zip(cls, v))) for p, v in zip(players, values)]

    def test_stock_rows_and_the_four_player_row_up_to_64(self):
        obj = SimpleNamespace(
            ExpAwardWeights=self.rows(('KillerExpBonus', 'ExpWeight'), range(1, 5), (0, 1), (0.04, 0.9), (0.05, 0.85),
                                      (0.06, 0.8)),
            KillSkillDurationsPerPlayers=self.rows(('Duration',), [0, 1, 2, 99], *[(1.0,)] * 4))  # the original patch
        ns = load({'GD_Globals.General.Globals': obj})
        ns['apply_globals'](None)
        self.assertEqual(ns['_globals_status']['changed'], ['ExpAwardWeights', 'KillSkillDurationsPerPlayers'])
        experience = [(r.Players, r.KillerExpBonus, r.ExpWeight) for r in obj.ExpAwardWeights]
        self.assertEqual(experience[:4], [(1, 0.0, 1.0), (2, 0.04, 0.9), (3, 0.05, 0.85), (4, 0.06, 0.8)])
        self.assertEqual(experience[4:], [(p, 0.06, 0.8) for p in range(5, 65)])
        durations = [(r.Players, r.Duration) for r in obj.KillSkillDurationsPerPlayers]
        self.assertEqual(durations, [(1, 7.0), (2, 8.0), (3, 9.0)] + [(p, 10.0) for p in range(4, 65)])
        ns['apply_globals'](None)
        self.assertEqual(ns['_globals_status'], dict(status='read_back', rows=64, changed=[]))

    def test_pending_until_loaded(self):
        ns = load({})
        ns['apply_globals'](None)
        self.assertEqual(ns['_globals_status']['status'], 'pending')


class OptionTests(unittest.TestCase):
    def test_defaults(self):
        calls = {node.targets[0].id: node.value for node in tree.body if isinstance(node, ast.Assign)
                 and isinstance(node.value, ast.Call) and getattr(node.value.func, 'id', '').endswith('Option')}
        def literal(name):
            call = calls[name]
            return [ast.literal_eval(a) for a in call.args[1:]], {k.arg: ast.literal_eval(k.value) for k in call.keywords
                                                                  if k.arg != 'description'}
        self.assertEqual(literal('stronger_enemies'), ([True], {}))
        self.assertEqual(literal('enemy_strength'), ([100], dict(min_value=0, max_value=200, step=25)))
        self.assertEqual(literal('more_enemies'), ([False], {}))
        self.assertEqual(literal('instant_travel'), ([False], {}))


if __name__ == '__main__': unittest.main()
