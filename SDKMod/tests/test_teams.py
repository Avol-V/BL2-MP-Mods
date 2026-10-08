"""Offline checks of team assignment: at most four players per team, at every moment."""
import ast
import random
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
FUNCTIONS = ('plan_teams', 'team_sizes', 'team_index', 'is_player', 'player_pris', 'ensure_team', 'needs_move',
             'apply_teams', 'pick_team')
CONSTANTS = ('TEAM_LIMIT', 'AI_TEAM', 'NO_TEAM', 'SQUADS', 'UNGROUPED', 'CHECK_INTERVAL')
chosen = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        node.decorator_list = []
        chosen.append(node)
    elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and (t.id in CONSTANTS or t.id.startswith('_')) for t in node.targets):
        chosen.append(node)
code = compile(ast.Module(body=chosen, type_ignores=[]), 'isolated_teams', 'exec')
BLOCK = object()


class Team:
    def __init__(self, index, name):
        self.TeamIndex, self.Name, self.Size = index, name, 0


class Controller:
    def __init__(self, player=True):
        self.Class = SimpleNamespace(_inherits=lambda base: player and base == 'PlayerController class')
        self.PlayerReplicationInfo = None


class PRI:
    def __init__(self, team=None, player=True, spectator=False):
        self.Team, self.bOnlySpectator = team, spectator
        self.Owner = Controller(player)
        self.Owner.PlayerReplicationInfo = self


class Game:
    """WillowCoopGameInfo team code as decompiled; records the fullest team after every change."""

    def __init__(self):
        self.Teams = []
        self.GameReplicationInfo = SimpleNamespace(PRIArray=[])
        self.WorldInfo = SimpleNamespace(NetMode=2)
        self.peak = 0
        self.InitializeTeams()

    def InitializeTeams(self):
        self.CreateTeam(0, 'Players')
        self.CreateTeam(1, 'AI')

    def CreateTeam(self, index, name):
        while len(self.Teams) <= index:  # UnrealScript grows the array on assignment
            self.Teams.append(None)
        self.Teams[index] = Team(index, name)

    def ChangeTeam(self, other, n, _new):
        if len(self.Teams) < 2:
            self.InitializeTeams()
        pri = other.PlayerReplicationInfo
        if n != 255 and pri.Team is not None and pri.Team is self.Teams[n]:
            return True
        if pri.Team is not None:
            pri.Team.Size -= 1  # RemoveFromTeam
            pri.Team = None
        ok = n == 255 or (n < len(self.Teams) and self.Teams[n] is not None)
        if n != 255 and ok:
            pri.Team = self.Teams[n]
            pri.Team.Size += 1
        counts = {}
        for p in self.GameReplicationInfo.PRIArray:
            if p.Team is not None:
                counts[p.Team.TeamIndex] = counts.get(p.Team.TeamIndex, 0) + 1
        self.peak = max([self.peak, *counts.values()])
        return ok

    def join(self, index):
        """Login: PickTeam result, then a new PRI and ChangeTeam."""
        pri = PRI()
        self.GameReplicationInfo.PRIArray.append(pri)
        self.ChangeTeam(pri.Owner, index, False)
        return pri

    def indices(self):
        return [None if p.Team is None else p.Team.TeamIndex for p in self.GameReplicationInfo.PRIArray]


def load(mode):
    ns = dict(team_mode=SimpleNamespace(value=mode), Block=BLOCK, errors=[],
              logging=SimpleNamespace(info=lambda *_: None),
              unrealsdk=SimpleNamespace(find_class=lambda name: name + ' class'))
    ns['logging'].error = ns['errors'].append
    exec(code, ns)
    return ns


def pick(ns, game, controller=None, num=255):
    return ns['pick_team'](game, SimpleNamespace(C=controller, Num=num), None, None)


def session(ns, players):
    """A host game the way the mod builds it: every player joins through PickTeam."""
    game = Game()
    for _ in range(players):
        game.join(pick(ns, game)[1])
    return game


class PlanTests(unittest.TestCase):
    def plan(self, current, mode):
        return load(mode)['plan_teams'](current, mode)

    def test_up_to_four_share_team_zero(self):
        for mode in ('Squads of 4', 'No teams'):
            self.assertEqual(self.plan([], mode), [])
            self.assertEqual(self.plan([None] * 4, mode), [0] * 4)
            self.assertEqual(self.plan([2, None, 1, 0], mode), [0] * 4)

    def test_no_teams_above_four(self):
        self.assertEqual(self.plan([0, 0, 0, 0, None], 'No teams'), [None] * 5)

    def test_squads_fill_the_first_team_with_room(self):
        squads = 'Squads of 4'
        self.assertEqual(self.plan([0, 0, 0, 0, None], squads), [0, 0, 0, 0, 2])
        self.assertEqual(self.plan([None] * 9, squads), [0] * 4 + [2] * 4 + [3])
        self.assertEqual(self.plan([0, 0, 0, 2, 2], squads), [0, 0, 0, 2, 2], 'squads stay together')
        self.assertEqual(self.plan([0, 0, 0, 2, 2, None], squads)[-1], 0)
        self.assertEqual(self.plan([1, 0, 0, 0, 0, 0], squads), [2, 0, 0, 0, 0, 2], 'no AI team, no fifth')

    def test_invariants(self):
        rng = random.Random(8)
        for _ in range(2000):
            current = [rng.choice([None, 0, 1, 2, 3, 5]) for _ in range(rng.randrange(13))]
            for mode in ('Squads of 4', 'No teams'):
                plan = self.plan(current, mode)
                self.assertEqual(len(plan), len(current))
                if len(current) <= 4:
                    self.assertEqual(plan, [0] * len(current))
                elif mode == 'No teams':
                    self.assertEqual(plan, [None] * len(current))
                else:
                    self.assertNotIn(None, plan)
                    self.assertNotIn(1, plan)
                    self.assertTrue(all(plan.count(i) <= 4 for i in plan), (current, plan))
                    kept = {}
                    for old, new in zip(current, plan):  # the first four of a valid team keep it
                        if old not in (None, 1) and kept.get(old, 0) < 4:
                            kept[old] = kept.get(old, 0) + 1
                            self.assertEqual(new, old)


class ApplyTests(unittest.TestCase):
    def apply(self, ns, game):
        ns['apply_teams'](SimpleNamespace(WorldInfo=SimpleNamespace(Game=game)))

    def test_fifth_player_without_teams(self):
        ns = load('No teams')
        game = session(ns, 4)
        self.assertEqual(game.indices(), [0] * 4)
        self.assertEqual(pick(ns, game), (BLOCK, 255))
        game.join(255)
        self.apply(ns, game)
        self.assertEqual(game.indices(), [None] * 5)
        self.assertLessEqual(game.peak, 4)
        self.assertEqual(ns['_teams_status'], dict(mode='No teams', sizes={'none': 5}))

    def test_fifth_player_starts_a_squad(self):
        ns = load('Squads of 4')
        game = session(ns, 9)
        self.assertEqual(game.indices(), [0] * 4 + [2] * 4 + [3])
        self.apply(ns, game)
        self.assertEqual(game.indices(), [0] * 4 + [2] * 4 + [3], 'nothing to move')
        self.assertEqual(game.peak, 4)
        self.assertEqual(ns['_teams_status']['sizes'], {'0': 4, '2': 4, '3': 1})

    def test_back_to_four_shares_team_zero(self):
        for mode in ('Squads of 4', 'No teams'):
            ns = load(mode)
            game = session(ns, 5)
            self.apply(ns, game)
            del game.GameReplicationInfo.PRIArray[1]  # a player leaves
            self.apply(ns, game)
            self.assertEqual(game.indices(), [0] * 4, mode)
            self.assertLessEqual(game.peak, 4)

    def test_mode_switch_in_session(self):
        ns = load('Squads of 4')
        game = session(ns, 6)
        ns['team_mode'].value = 'No teams'
        self.apply(ns, game)
        self.assertEqual(game.indices(), [None] * 6)
        ns['team_mode'].value = 'Squads of 4'
        self.apply(ns, game)
        self.assertEqual(game.indices(), [0] * 4 + [2] * 2)
        self.assertLessEqual(game.peak, 4)

    def test_join_waits_until_the_team_has_room(self):
        ns = load('Squads of 4')
        game = session(ns, 5)
        pris = game.GameReplicationInfo.PRIArray
        pris.insert(3, pris.pop())  # the squad-2 player comes before the fourth one in team 0
        ns['plan_teams'] = lambda current, mode: [0, 0, 0, 0, 2]  # swap them
        self.apply(ns, game)
        self.assertEqual(game.indices(), [0, 0, 0, 2, 2], 'the join waits, the leave happens')
        self.apply(ns, game)
        self.assertEqual(game.indices(), [0, 0, 0, 0, 2])
        self.assertLessEqual(game.peak, 4)

    def test_squad_team_carried_over_by_travel(self):
        ns = load('Squads of 4')
        game = Game()  # the new GameInfo: teams 0 and 1 only
        pris = game.GameReplicationInfo.PRIArray
        for _ in range(4):
            game.join(0)
        stale = PRI(team=Team(2, 'Squad 2'))
        pris.append(stale)
        self.apply(ns, game)
        self.assertIs(stale.Team, game.Teams[2])
        self.assertEqual(game.indices(), [0] * 4 + [2])

    def test_spectators_and_other_controllers_are_not_counted(self):
        ns = load('Squads of 4')
        game = session(ns, 4)
        pris = game.GameReplicationInfo.PRIArray
        pris += [PRI(spectator=True), PRI(player=False)]
        self.apply(ns, game)
        self.assertEqual(game.indices(), [0] * 4 + [None, None])

    def test_pick_team_guards(self):
        ns = load('Squads of 4')
        game = session(ns, 1)
        game.WorldInfo.NetMode = 3
        self.assertIsNone(pick(ns, game), 'clients do not choose teams')
        game.WorldInfo.NetMode = 2
        self.assertEqual(pick(ns, game, Controller(player=False), num=7), (BLOCK, 7))
        game.GameReplicationInfo = None
        self.assertEqual(pick(ns, game), (BLOCK, 255), 'an error falls back to no team')
        self.assertEqual(len(ns['errors']), 1)


if __name__ == '__main__': unittest.main()
