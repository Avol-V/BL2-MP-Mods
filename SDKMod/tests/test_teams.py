"""Offline checks of team assignment: at most four players per team, at every moment."""
import ast
import random
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
FUNCTIONS = ('plan_teams', 'team_sizes', 'team_index', 'is_player', 'player_pris', 'ensure_team', 'needs_move',
             'apply_teams', 'pick_team', 'initialize_teams')
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
    """WillowCoopGameInfo team code as decompiled; records the fullest team after every change.

    initialize_teams: a POST hook on InitializeTeams, as the mod installs it.
    """

    def __init__(self, initialize_teams=None):
        self.Teams = []
        self.GameReplicationInfo = SimpleNamespace(PRIArray=[])
        self.WorldInfo = SimpleNamespace(NetMode=2)
        self.peak = 0
        self.changes = 0
        self.hook = initialize_teams
        self.InitializeTeams()

    def InitializeTeams(self):
        self.CreateTeam(0, 'Players')
        self.CreateTeam(1, 'AI')
        if self.hook is not None:
            self.hook(self, None, None, None)

    def CreateTeam(self, index, name):
        while len(self.Teams) <= index:  # UnrealScript grows the array on assignment
            self.Teams.append(None)
        self.Teams[index] = Team(index, name)

    def ChangeTeam(self, other, n, _new):
        self.changes += 1
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
        self.record_peak()
        return ok

    def record_peak(self):
        """The HUD compares team indices, not team objects: a stale team counts as its index."""
        counts = {}
        for p in self.GameReplicationInfo.PRIArray:
            if p.Team is not None:
                counts[p.Team.TeamIndex] = counts.get(p.Team.TeamIndex, 0) + 1
        self.peak = max([self.peak, *counts.values()])

    def HandleSeamlessTravelPlayer(self, other):
        pri = other.PlayerReplicationInfo
        old = pri.Team
        if old is not None and old.TeamIndex < len(self.Teams) and self.Teams[old.TeamIndex] is not old:
            new = self.Teams[old.TeamIndex]
            if old.Size <= 1:
                old.destroyed = True  # Destroy(); the PRI keeps pointing at it until AddToTeam
            else:
                old.Size -= 1  # RemoveFromTeam
                pri.Team = None
            if new is not None:  # AddToTeam; on none it is an "Accessed None" no-op
                new.Size += 1
                pri.Team = new
        self.record_peak()

    def seamless_travel(self, initialize_teams=None):
        """The new GameInfo's PostSeamlessTravel: InitializeTeams, then HandleSeamlessTravelPlayer for
        every player. PRIs travel with their old team objects; the new GRI collects them."""
        new = Game(initialize_teams)
        new.GameReplicationInfo.PRIArray = list(self.GameReplicationInfo.PRIArray)
        for pri in new.GameReplicationInfo.PRIArray:
            new.HandleSeamlessTravelPlayer(pri.Owner)
        return new

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


def apply(ns, game):
    ns['apply_teams'](SimpleNamespace(WorldInfo=SimpleNamespace(Game=game)))


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


class TravelTests(unittest.TestCase):
    """WillowCoopGameInfo.PostSeamlessTravel: InitializeTeams, then HandleSeamlessTravelPlayer per player."""

    def squads(self, ns, players):
        game = session(ns, players)
        apply(ns, game)  # a pass remembers the squad teams in use
        return game

    def assert_moved(self, game):
        pris = game.GameReplicationInfo.PRIArray
        for pri in pris:
            self.assertIs(pri.Team, game.Teams[pri.Team.TeamIndex], 'on a team of the new GameInfo')
        for team in game.Teams:
            self.assertEqual(team.Size, sum(p.Team is team for p in pris), 'team size')

    def test_without_the_hook_squads_stay_on_old_teams(self):
        ns = load('Squads of 4')
        old = self.squads(ns, 9)
        new = old.seamless_travel()  # up to 1.3.0
        pris = new.GameReplicationInfo.PRIArray
        self.assertEqual([p.Team in new.Teams for p in pris], [True] * 4 + [False] * 5)
        apply(ns, new)
        self.assert_moved(new)
        self.assertEqual(new.changes, 5, 'apply_teams moved the squads, up to 2 s later')
        self.assertLessEqual(new.peak, 4)

    def test_with_the_hook_the_game_moves_squads(self):
        ns = load('Squads of 4')
        old = self.squads(ns, 9)
        new = old.seamless_travel(ns['initialize_teams'])
        self.assert_moved(new)
        self.assertEqual(new.indices(), [0] * 4 + [2] * 4 + [3])
        self.assertEqual([t.Size for t in new.Teams], [4, 0, 4, 1])
        self.assertEqual([getattr(t, 'destroyed', False) for t in old.Teams], [True, False, True, True])
        self.assertLessEqual(new.peak, 4)
        apply(ns, new)
        self.assertEqual(new.changes, 0, 'nothing left for apply_teams')

    def test_a_join_since_the_last_pass_is_remembered(self):
        ns = load('Squads of 4')
        old = session(ns, 5)  # the fifth joined through PickTeam, no pass before travel
        new = old.seamless_travel(ns['initialize_teams'])
        self.assert_moved(new)
        self.assertEqual(new.indices(), [0] * 4 + [2])

    def test_no_gap_below_a_squad(self):
        ns = load('Squads of 4')
        old = self.squads(ns, 9)
        del old.GameReplicationInfo.PRIArray[4:8]  # squad 2 leaves, squad 3 stays together
        apply(ns, old)
        self.assertEqual(old.indices(), [0] * 4 + [3])
        new = old.seamless_travel(ns['initialize_teams'])
        self.assertIsNotNone(new.Teams[2], 'without team 2 the game would drop squad 3 from its team')
        self.assert_moved(new)
        self.assertEqual(new.indices(), [0] * 4 + [3])

    def test_squads_through_several_travels_and_joins(self):
        ns = load('Squads of 4')
        game = self.squads(ns, 6)
        for players in (7, 9, 10, 8):
            game = game.seamless_travel(ns['initialize_teams'])
            self.assert_moved(game)
            self.assertLessEqual(game.peak, 4)
            pris = game.GameReplicationInfo.PRIArray
            while len(pris) > players:
                del pris[1]
            while len(pris) < players:
                game.join(pick(ns, game)[1])
            apply(ns, game)
            apply(ns, game)
            self.assertLessEqual(game.peak, 4)
            self.assertTrue(all(game.indices().count(i) <= 4 for i in game.indices()))

    def test_nothing_created_without_squads(self):
        for mode, players in (('Squads of 4', 4), ('No teams', 6)):
            ns = load(mode)
            old = self.squads(ns, players)
            new = old.seamless_travel(ns['initialize_teams'])
            self.assertEqual(len(new.Teams), 2, mode)

    def test_hook_guards(self):
        ns = load('Squads of 4')
        ns['_squad_teams'] = {2}
        game = Game()
        game.WorldInfo.NetMode = 3
        ns['initialize_teams'](game, None, None, None)
        self.assertEqual(len(game.Teams), 2, 'clients have no GameInfo teams to create')
        game.WorldInfo.NetMode = 2
        game.CreateTeam = None
        ns['initialize_teams'](game, None, None, None)
        self.assertEqual(len(ns['errors']), 1, 'an error is logged, travel goes on')


if __name__ == '__main__': unittest.main()
