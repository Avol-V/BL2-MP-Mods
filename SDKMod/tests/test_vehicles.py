"""Offline checks of the vehicle options: off by default, applied by class, stock values restored."""
import ast
import enum
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / 'unlimited_coop'
tree = ast.parse((source/'__init__.py').read_text())
FUNCTIONS = ('plain', 'vehicle_writes', 'apply_definition', 'apply_vehicles', 'vehicle_spawned')
NAMES = ('VEHICLE_TWEAKS', '_vehicle_stock', '_vehicles_status')
chosen = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        node.decorator_list = []
        chosen.append(node)
    elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in NAMES for t in node.targets):
        chosen.append(node)
code = compile(ast.Module(body=chosen, type_ignores=[]), 'isolated_vehicles', 'exec')
Tag = enum.IntFlag('EVehicleSpawnStationAvailability', dict(Land=0, Desert=1, Ice=2, Wheeled=4, Hovercraft=5,
                                                            BL2Main=20, DLCOrchid=21, DLCSage=23))


class Definition:
    def __init__(self, path, **props):
        self.path = path
        self.Name = path.rsplit('.', 1)[-1]
        self.__dict__.update(props)

    def _path_name(self): return self.path


def station(path, required, supported):
    return Definition(path, RequiredTags=[Tag(t) for t in required], SupportedTags=[Tag(t) for t in supported])


def stock():
    """Stock values from the BLCMM object dumps (docs: tools/dumps.py find RequiredTags VSSUIDefinition)."""
    return {
        'ChassisDefinition': [Definition('GD_Runner_Streaming.Archetype.Chassis_RocketRunner',
                                         AllowPawnsToStandOnTopOfVehicle=False),
                              Definition('GD_Sage_FanBoat.Vehicle.Chassis_FanBoat', AllowPawnsToStandOnTopOfVehicle=True),
                              Definition('WillowGame.Default__ChassisDefinition', AllowPawnsToStandOnTopOfVehicle=False)],
        'VehicleSpawnStationGFxDefinition': [station('UI_VehicleSpawnStation.VehicleSpawnStation_Definition', [20], [0, 4]),
                                             station('Sage_UI_VehicleSpawnStation.VehicleSpawnStation_Definition', [23], [0, 5])],
        'VSSUIDefinition': [station('GD_Globals.VehicleSpawnStation.VSSUI_MGRunner', [20, 0, 4], [2, 1]),
                            station('GD_SagePackageDef.Vehicles.VSSUI_ShockFanBoat', [23, 5], [0, 1, 2])],
        'VehicleFamilyDefinition': [station('GD_Globals.VehicleSpawnStation.VehicleFamily_BanditTechnical',
                                            [20, 0, 4], [2, 1])],
    }


def load():
    ns = dict(stand_on_vehicles=SimpleNamespace(value=False), any_vehicle_station=SimpleNamespace(value=False),
              logged=[], errors=[])
    ns['logging'] = SimpleNamespace(info=ns['logged'].append, error=ns['errors'].append)
    exec(code, ns)
    return ns


def values(objects, cls):
    tweak = load()['VEHICLE_TWEAKS'][cls][1]
    return {o.path: {p: o.__dict__[p] for p in tweak} for o in objects}


class OptionTests(unittest.TestCase):
    def test_options_are_off_by_default(self):
        options = {node.targets[0].id: node.value for node in tree.body if isinstance(node, ast.Assign)
                   and isinstance(node.value, ast.Call) and getattr(node.value.func, 'id', None) == 'BoolOption'}
        for name in ('stand_on_vehicles', 'any_vehicle_station'):
            self.assertIs(ast.literal_eval(options[name].args[1]), False, name)

    def test_tweaks_leave_unlocks_and_previews_alone(self):
        tweaks = load()['VEHICLE_TWEAKS']
        self.assertEqual(set(tweaks), set(stock()))
        for _, tweak in tweaks.values():
            self.assertFalse({'RequiredMissionCompletionToUnlock', 'VehiclePreviewClip'} & set(tweak))


class WritesTests(unittest.TestCase):
    def setUp(self):
        self.writes = load()['vehicle_writes']

    def test_on_keeps_stock_once_and_writes_the_tweak(self):
        tweak = dict(RequiredTags=[20], SupportedTags=[0, 4])
        current = dict(RequiredTags=[23], SupportedTags=[0, 5])
        self.assertEqual(self.writes(current, None, tweak, True), (dict(RequiredTags=[20], SupportedTags=[0, 4]), current))
        self.assertEqual(self.writes(tweak, current, tweak, True), ({}, current), 'applied: nothing to write')
        self.assertEqual(self.writes(dict(tweak, RequiredTags=[23]), current, tweak, True),
                         (dict(RequiredTags=[20]), current), 'reloaded with stock values: written again')

    def test_off_restores_and_forgets(self):
        tweak = dict(AllowPawnsToStandOnTopOfVehicle=True)
        kept = dict(AllowPawnsToStandOnTopOfVehicle=False)
        self.assertEqual(self.writes(tweak, kept, tweak, False), (kept, None))
        self.assertEqual(self.writes(kept, kept, tweak, False), ({}, None))
        self.assertEqual(self.writes(tweak, None, tweak, False), ({}, None), 'never changed: left alone')

    def test_tweak_matching_stock_is_kept_as_stock(self):
        tweak = dict(AllowPawnsToStandOnTopOfVehicle=True)
        self.assertEqual(self.writes(tweak, None, tweak, True), ({}, tweak))


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.ns = load()
        self.objects = stock()
        self.before = {cls: values(objs, cls) for cls, objs in self.objects.items()}
        self.ns['unrealsdk'] = SimpleNamespace(find_all=lambda cls: list(self.objects[cls]))

    def apply(self):
        for cls in self.objects:
            self.ns['apply_vehicles'](None, cls)

    def test_off_by_default_changes_nothing(self):
        self.apply()
        self.assertEqual({cls: values(objs, cls) for cls, objs in self.objects.items()}, self.before)
        self.assertEqual(self.ns['_vehicle_stock'], {})

    def test_stand_on_vehicles(self):
        self.ns['stand_on_vehicles'].value = True
        self.apply()
        chassis = self.objects['ChassisDefinition']
        self.assertEqual([c.AllowPawnsToStandOnTopOfVehicle for c in chassis], [True, True, False], 'not the defaults')
        self.assertEqual(self.ns['_vehicles_status']['ChassisDefinition'], dict(on=True, loaded=2, changed=1))
        stations = self.objects['VehicleSpawnStationGFxDefinition']
        self.assertEqual(values(stations, 'VehicleSpawnStationGFxDefinition'),
                         self.before['VehicleSpawnStationGFxDefinition'], 'the other option stays off')
        self.ns['stand_on_vehicles'].value = False
        self.apply()
        self.assertEqual(values(chassis, 'ChassisDefinition'), self.before['ChassisDefinition'])
        self.assertNotIn('ChassisDefinition', self.ns['_vehicle_stock'])
        self.assertEqual(self.ns['_vehicles_status']['ChassisDefinition'], dict(on=False, loaded=2, changed=0))

    def test_any_vehicle_station_and_back(self):
        self.ns['any_vehicle_station'].value = True
        self.apply()
        station, dlc_station = self.objects['VehicleSpawnStationGFxDefinition']
        self.assertEqual((dlc_station.RequiredTags, dlc_station.SupportedTags), ([20], [0, 4]))
        for cls in ('VSSUIDefinition', 'VehicleFamilyDefinition'):
            for definition in self.objects[cls]:
                self.assertEqual((definition.RequiredTags, definition.SupportedTags), ([0, 20], [0, 1, 2]))
        self.assertEqual(self.ns['_vehicles_status']['VehicleSpawnStationGFxDefinition'],
                         dict(on=True, loaded=2, changed=1), 'the main-game station already matches')
        self.apply()
        self.assertEqual(len(self.ns['logged']), 4, 'a status is logged when it changes')
        self.ns['any_vehicle_station'].value = False
        self.apply()
        self.assertEqual({cls: values(objs, cls) for cls, objs in self.objects.items()}, self.before)
        self.assertEqual(self.ns['_vehicle_stock'], {})

    def test_definitions_loaded_later_and_reloaded(self):
        self.ns['any_vehicle_station'].value = True
        family = self.objects['VehicleFamilyDefinition']
        later = station('GD_OrchidPackageDef.Vehicles.VehicleFamily_Hovercraft', [21, 5], [0, 1, 2])
        self.apply()
        family.append(later)  # a DLC map loads its definitions
        self.apply()
        self.assertEqual(later.RequiredTags, [0, 20])
        family[1] = station(later.path, [21, 5], [0, 1, 2])  # unloaded and loaded again with stock values
        self.apply()
        self.assertEqual(family[1].RequiredTags, [0, 20])
        del family[1]  # not loaded while the option is turned off
        self.ns['any_vehicle_station'].value = False
        self.apply()
        self.assertNotIn('VehicleFamilyDefinition', self.ns['_vehicle_stock'], 'stock of unloaded ones forgotten')
        self.assertEqual(values(family, 'VehicleFamilyDefinition'), self.before['VehicleFamilyDefinition'])

    def test_readback_mismatch_is_an_error(self):
        class Const(Definition):
            def __setattr__(self, name, value):
                if name != 'AllowPawnsToStandOnTopOfVehicle':
                    super().__setattr__(name, value)
        self.objects['ChassisDefinition'] = [Const('GD.Chassis', AllowPawnsToStandOnTopOfVehicle=False)]
        self.ns['stand_on_vehicles'].value = True
        self.ns['apply_vehicles'](None, 'ChassisDefinition')
        self.assertIn('Readback differs', self.ns['_vehicles_status']['ChassisDefinition']['error'])


class SpawnTests(unittest.TestCase):
    """Chassis of player vehicles load with the vehicle, after the passes of a map change."""

    def setUp(self):
        self.ns = load()
        self.loaded = []
        self.ns['unrealsdk'] = SimpleNamespace(find_all=lambda cls: list(self.loaded) if cls == 'ChassisDefinition' else [])

    def spawn(self, chassis):
        self.loaded.append(chassis)
        self.ns['vehicle_spawned'](SimpleNamespace(ChassisDef=chassis), None, None, None)

    def test_spawned_vehicle_gets_the_tweak_and_loses_it_when_off(self):
        runner = Definition('GD_Runner_Streaming.Archetype.Chassis_RocketRunner', AllowPawnsToStandOnTopOfVehicle=False)
        self.spawn(runner)
        self.assertIs(runner.AllowPawnsToStandOnTopOfVehicle, False, 'option off: untouched')
        self.ns['stand_on_vehicles'].value = True
        technical = Definition('GD_BTech_Streaming.ChassisDefinition.Chassis_CatapultTechnical',
                               AllowPawnsToStandOnTopOfVehicle=False)
        self.spawn(technical)
        self.assertIs(technical.AllowPawnsToStandOnTopOfVehicle, True)
        self.ns['vehicle_spawned'](SimpleNamespace(ChassisDef=None), None, None, None)
        self.ns['apply_vehicles'](None, 'ChassisDefinition')
        self.assertIs(runner.AllowPawnsToStandOnTopOfVehicle, True, 'loaded before the option: the pass')
        self.ns['stand_on_vehicles'].value = False
        self.ns['apply_vehicles'](None, 'ChassisDefinition')
        self.assertEqual([c.AllowPawnsToStandOnTopOfVehicle for c in self.loaded], [False, False])
        self.assertEqual(self.ns['errors'], [])

    def test_spawn_error_is_logged(self):
        self.ns['stand_on_vehicles'].value = True
        self.spawn(Definition('GD.Broken'))  # no such property
        self.assertEqual(len(self.ns['errors']), 1)


if __name__ == '__main__': unittest.main()
