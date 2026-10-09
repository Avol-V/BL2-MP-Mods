"""Offline checks of the map reload: the other map it picks, the Kismet entries it drops, and that every
population value it changes is back to stock when it ends, also when it stops early."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
FUNCTIONS = ('map_name', 'level_of', 'ready', 'arrived', 'loaded', 'pick_hop', 'population_master',
             'population_definitions', 'connected_trackers', 'wipe_kismet', 'arm', 'disarm', 'request_reload',
             'reload_request', 'reload_hop', 'reload_home', 'reload_step')
CONSTANTS = ('POPULATION_CLASSES', 'RESET_ON_LOAD', 'RELOAD_STEP', 'RELOAD_WAIT', 'RELOAD_SETTLE', 'RELOAD_GRACE',
             'MAP_ALIASES', 'NOT_A_MAP', 'RELOAD_STAGES')
chosen = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        node.decorator_list = []
        chosen.append(node)
    elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and (t.id in CONSTANTS or t.id == '_reload')
                                              for t in node.targets):
        chosen.append(node)
chosen.sort(key=lambda n: isinstance(n, ast.Assign) and n.targets[0].id == 'RELOAD_STAGES')  # after the stages
code = compile(ast.Module(body=chosen, type_ignores=[]), 'isolated_reload', 'exec')

DATA_TRUE = 'GD_Population_Shopping.VendingMachine.VendingMachine_Weapons'


class Obj(SimpleNamespace):
    def _path_name(self):
        return self.path


def definition(path, value=False):
    return Obj(path=path, Name=path.rsplit('.', 1)[-1], bTotalResetOnLevelLoad=value)


def station(level, dlc=None, send_only=False, closed=None, name=None):
    return SimpleNamespace(GetStationLevelName=lambda: level, DlcExpansion=dlc, bSendOnly=send_only,
                           InaccessibleObjective=closed, StationDisplayName=name or level)


def tracker(outer, name, value=0, loaded=True):
    return SimpleNamespace(OpportunityOutermostName=outer, OpportunityName=name, bTotalResetOnLevelLoad=value,
                           LoadedOpportunity=object() if loaded else None)


class World:
    """The engine as the reload sees it: maps with population definitions and trackers, the Kismet bank,
    class defaults and players. Loading a map loads its definitions; one not loaded before copies the
    class default unless its data sets the flag, as UE3 serialization does."""

    def __init__(self):
        self.maps = {'home_p': ['GD_A.Pop_Enemy', 'GD_A.Pop_Chest', DATA_TRUE],
                     'hop_p': ['GD_B.Pop_Enemy'], 'menumap': []}
        self.defaults = {c: Obj(path=f'Default__{c}', Name=f'Default__{c}', bTotalResetOnLevelLoad=False)
                         for c in ('PopulationDefinition', 'WillowPopulationDefinition')}
        self.loaded = {}
        self.reset_on_connect = {}
        self.trackers = []
        self.bank = Obj(Name='PersistentGameDataManager_0', path='bank', SequencesWithPersistentData=[])
        self.map = None
        self.travels = []
        self.home = station('Home_P', name='Home')
        self.stations = {'S_Home': self.home, 'S_Dlc': station('Dlc_P', dlc=object()), 'S_Hop': station('Hop_P'),
                         'S_Sanct': station('Sanctuary_P')}
        lookup = SimpleNamespace(FindFastTravelStationLookupObject=self.stations.get)
        willow = SimpleNamespace(GetFastTravelStationsLookup=lambda: lookup)
        self.pm = SimpleNamespace(OpportunityList=self.trackers)
        gearbox = SimpleNamespace(GetPopulationMaster=lambda: self.pm)
        self.cdos = {'WillowGlobals': SimpleNamespace(GetWillowGlobals=lambda: willow),
                     'GearboxGlobals': SimpleNamespace(GetGearboxGlobals=lambda: gearbox), **self.defaults}
        self.game = SimpleNamespace(TravelToStation=self.travel, TravelCountdownInProcess=lambda: False,
                                    CheckMapChangeConditions=lambda: True, GameReplicationInfo=None)
        self.pc = SimpleNamespace(
            WorldInfo=SimpleNamespace(GetMapName=lambda _: self.map, Game=self.game, NetMode=0, StreamingLevels=[]),
            Pawn=object(), LastVisitedTeleporter=self.home,
            ActivatedTeleportersList=['S_Home', 'S_Dlc', 'S_Sanct', 'S_Hop'],
            IsPauseMenuOpen=lambda: self.menu, PlayerReplicationInfo=SimpleNamespace(bGFxMenuOpen=0),
            IsLoadingMoviePlaying=lambda: False, _get_address=lambda: 1)
        self.commit = None  # the map_ready hook: PostCommitMapChange
        self.menu = False
        self.players_ready = True
        self.load('home_p')

    def load(self, name, ticks=0):
        """Unload the current map (its trackers keep their state), load another."""
        self.map = name
        for t in self.trackers:
            t.LoadedOpportunity = None
        self.loaded = {}
        for path in self.maps.get(name, []):
            value = path == DATA_TRUE or self.defaults['WillowPopulationDefinition'].bTotalResetOnLevelLoad
            self.loaded[path] = definition(path, value)
        for path, d in self.loaded.items():
            key = (name, path)
            old = next((t for t in self.trackers if (t.OpportunityOutermostName, t.OpportunityName) == key), None)
            if old is None:
                old = tracker(*key)
                self.trackers.append(old)
            old.LoadedOpportunity = object()
            old.bTotalResetOnLevelLoad = int(d.bTotalResetOnLevelLoad)
            if d.bTotalResetOnLevelLoad:
                self.reset_on_connect[key] = self.reset_on_connect.get(key, 0) + 1
        self.bank.SequencesWithPersistentData.append(SimpleNamespace(LevelPackageName=name.capitalize()))

    def travel(self, station_):
        self.travels.append(station_)
        self.load(str(station_.GetStationLevelName()).lower())
        if self.commit:
            self.commit()

    def find_all(self, cls, _exact):
        if cls == 'PersistentGameDataManager':
            return [self.defaults['PopulationDefinition'], self.bank]
        if cls == 'WillowPopulationDefinition':
            return list(self.loaded.values()) + [self.defaults[cls]]
        return [self.defaults[cls]]

    def find_class(self, cls):
        return SimpleNamespace(ClassDefaultObject=self.cdos[cls])

    def stock(self):
        """Every loaded definition and class default has its game-data value, every connected tracker too."""
        defs = all(d.bTotalResetOnLevelLoad == (p == DATA_TRUE) for p, d in self.loaded.items())
        cdos = not any(d.bTotalResetOnLevelLoad for d in self.defaults.values())
        trackers = all(t.bTotalResetOnLevelLoad == int(t.OpportunityName == DATA_TRUE)
                       for t in self.trackers if t.LoadedOpportunity is not None)
        return defs and cdos and trackers


class ReloadTest(unittest.TestCase):
    def setUp(self):
        self.world = w = World()
        self.messages = []
        self.players = [SimpleNamespace(Owner=w.pc)]
        self.ns = dict(unrealsdk=SimpleNamespace(find_all=w.find_all, find_class=w.find_class),
                       logging=SimpleNamespace(info=lambda *_: None, error=lambda *_: None),
                       say=self.messages.append, is_host=lambda pc: pc.WorldInfo.NetMode != 3,
                       player_pris=lambda _game: self.players)
        exec(code, self.ns)
        self.ns['ready'] = lambda _c: w.players_ready  # replaced after exec: the real one needs an engine
        w.commit = self.commit

    def commit(self):
        if self.ns['_reload'] is not None:
            self.ns['_reload']['commits'] += 1

    def client(self, address):
        controller = SimpleNamespace(_get_address=lambda: address)
        self.players.append(SimpleNamespace(Owner=controller))
        return controller

    def report(self, controller, package):
        """The level_visible hook."""
        self.ns['_reload']['visible'].setdefault(controller._get_address(), set()).add(package)

    def run_until_done(self, start=0.0, limit=400):
        now = start
        for _ in range(limit):
            if self.ns['_reload'] is None:
                return now
            if now >= self.ns['_reload']['next']:
                self.ns['reload_step'](self.world.pc, now)
            now += 0.25
        self.fail('reload did not end')

    def test_pick_hop_skips_this_map_dlc_and_sanctuary(self):
        hop = self.ns['pick_hop'](self.world.pc, self.world.home)
        self.assertIs(hop, self.world.stations['S_Hop'])
        self.world.pc.ActivatedTeleportersList = ['S_Home', 'S_Dlc', 'S_Sanct']
        self.assertIsNone(self.ns['pick_hop'](self.world.pc, self.world.home))
        self.world.stations['S_Closed'] = station('Closed_P', closed=object())
        self.world.stations['S_Send'] = station('Send_P', send_only=True)
        self.world.pc.ActivatedTeleportersList = ['S_Closed', 'S_Send']
        self.assertIsNone(self.ns['pick_hop'](self.world.pc, self.world.home))

    def test_reload_resets_home_only_and_restores_stock(self):
        w = self.world
        self.ns['request_reload']()
        self.run_until_done()
        self.assertEqual([s.GetStationLevelName() for s in w.travels], ['Hop_P', 'Home_P'])
        self.assertEqual(self.messages[-1], 'Map reloaded.')
        self.assertEqual(w.map, 'home_p')
        # every home definition reset on the return, the other map never
        self.assertEqual({k for k in w.reset_on_connect if k[0] == 'home_p'},
                         {('home_p', p) for p in w.maps['home_p']})
        self.assertNotIn(('hop_p', 'GD_B.Pop_Enemy'), w.reset_on_connect)
        self.assertTrue(w.stock())
        # Kismet entries of home were dropped on the other map; home's new entry came with the return
        self.assertEqual([e.LevelPackageName for e in w.bank.SequencesWithPersistentData], ['Hop_p', 'Home_p'])

    def test_waits_for_menus_and_ready_players(self):
        w = self.world
        w.menu = True
        self.ns['request_reload']()
        for i in range(10):
            self.ns['reload_step'](w.pc, i)
        self.assertEqual(w.travels, [])
        w.menu = False
        self.ns['reload_step'](w.pc, 20)
        self.assertEqual(w.map, 'hop_p')
        w.players_ready = False
        for i in range(10):
            self.ns['reload_step'](w.pc, 21 + i)
        self.assertEqual(w.map, 'hop_p')
        w.players_ready = True
        self.run_until_done(40)
        self.assertEqual(w.map, 'home_p')
        self.assertTrue(w.stock())

    def test_stops_without_changes_if_players_never_ready(self):
        w = self.world
        w.players_ready = False
        self.ns['request_reload']()
        self.run_until_done(limit=1000)
        self.assertEqual(w.map, 'hop_p')
        self.assertTrue(self.messages[-1].startswith('Map reload stopped'))
        self.assertEqual({k for k in w.reset_on_connect if k[0] == 'home_p'}, {('home_p', DATA_TRUE)})  # stock
        self.assertTrue(w.stock())

    def test_quit_to_menu_restores_stock(self):
        w = self.world
        self.ns['request_reload']()
        self.ns['reload_step'](w.pc, 0)  # leaves for the other map
        self.ns['reload_step'](w.pc, 1)
        w.game.TravelToStation = lambda _s: w.load("menumap")  # the host quits on the way home
        self.ns['reload_step'](w.pc, 2)  # ready twice: armed, "travels"
        self.assertTrue(self.ns['_reload']['armed'])
        self.ns['reload_step'](w.pc, 3)
        self.assertIsNone(self.ns['_reload'])
        self.assertFalse(any(d.bTotalResetOnLevelLoad for d in w.defaults.values()))

    def test_waits_for_clients_to_report_the_other_map(self):
        w = self.world
        late = self.client(2)
        self.ns['request_reload']()
        self.ns['reload_step'](w.pc, 0)
        self.report(self.client(3), 'hop_p')
        for i in range(1, 60):
            self.ns['reload_step'](w.pc, i)
        self.assertEqual(w.map, 'hop_p')
        self.report(late, 'hop_p_dynamic')
        self.ns['reload_step'](w.pc, 60)
        self.ns['reload_step'](w.pc, 61)
        self.assertEqual(w.map, 'hop_p')
        self.report(late, 'hop_p')
        self.run_until_done(62)
        self.assertEqual(w.map, 'home_p')
        self.assertTrue(w.stock())

    def test_grace_for_clients_without_reports(self):
        w = self.world
        self.client(2)
        self.ns['request_reload']()
        self.ns['reload_step'](w.pc, 0)
        self.ns['reload_step'](w.pc, 1)  # the host arrived
        self.ns['reload_step'](w.pc, 1 + self.ns['RELOAD_GRACE'] - 1)
        self.ns['reload_step'](w.pc, 1 + self.ns['RELOAD_GRACE'] - 0.5)
        self.assertEqual(w.map, 'hop_p')
        self.run_until_done(1 + self.ns['RELOAD_GRACE'])
        self.assertEqual(w.map, 'home_p')

    def test_not_arrived_while_loading_or_before_commit(self):
        w = self.world
        loading = [True]
        w.pc.IsLoadingMoviePlaying = lambda: loading[0]
        self.ns['request_reload']()
        self.ns['reload_step'](w.pc, 0)
        for i in range(1, 10):
            self.ns['reload_step'](w.pc, i)
        self.assertEqual(w.map, 'hop_p')
        loading[0] = False
        self.run_until_done(10)
        self.assertEqual(w.map, 'home_p')

    def test_refusals(self):
        w = self.world
        w.pc.WorldInfo.NetMode = 3
        self.ns['request_reload']()
        self.run_until_done()
        self.assertEqual(self.messages[-1], 'Only the host can reload the map.')
        w.pc.WorldInfo.NetMode = 0
        w.pc.LastVisitedTeleporter = w.stations['S_Hop']
        self.ns['request_reload']()
        self.run_until_done()
        self.assertIn('another map', self.messages[-1])
        self.assertEqual(w.travels, [])

    def test_error_restores_stock(self):
        w = self.world
        self.ns['request_reload']()
        self.ns['reload_step'](w.pc, 0)
        self.ns['reload_step'](w.pc, 1)

        def broken(_station):
            raise RuntimeError('travel failed')
        w.game.TravelToStation = broken
        self.ns['reload_step'](w.pc, 2)
        self.assertIsNone(self.ns['_reload'])
        self.assertIn('travel failed', self.messages[-1])
        self.assertTrue(w.stock())


if __name__ == '__main__':
    unittest.main()
