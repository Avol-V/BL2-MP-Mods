"""Robeth v0.18 settings + AstrandPallas PickTeam hook, with load-aware application.

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
from mods_base import ENGINE, build_mod, hook, open_in_mod_dir, RestartToDisable
from mods_base.settings import SETTINGS_DIR

__version__: str
__version_info__: tuple[int, ...]
SOURCE_SHA256 = '804f7f740ee2c1d0c5ca6a1e9dec5cbce4c9a6d3c7cf09407ff1c3b56b9712da'
HOTFIX = re.compile(r'^#<hotfix><key>"([^"]*)"</key><value>",(.*)"</value><(on|off)>$')
TYPED = re.compile(r"^\w+'(.+)'$")


def parse_patch(text):
    records = []
    for raw in text.splitlines():
        line = raw.strip()
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
            records.append(dict(target=target, prop=prop, value=value, hotfix=key, hotfix_value=',' + body))
        elif line.lower().startswith('set '):
            if line.startswith(('set PlayerInput Bindings', 'set Transient.')):
                continue
            _, target, prop, value = line.split(None, 3)
            records.append(dict(target=target, prop=prop, value=value, hotfix=None))
    return records


with open_in_mod_dir(Path(__file__).with_name('cooppatch.txt'), binary=True) as stream:
    source = stream.read()
if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
    raise ValueError('Unexpected cooppatch.txt: review changes before enabling')
RECORDS = parse_patch(source.decode('utf8'))
COMMANDS = [f"set {r['target']} {r['prop']} {r['value']}" for r in RECORDS]
_seen = {}
_rows = {}
_next_check = 0.0
_world = None
_pick_calls = 0
_last_summary = None
_service_status = {'status': 'pending'}
_last_report = None
_last_service_status = None


def register_hotfixes():
    """Preserve unrelated service entries; select by service identity, never numeric suffix."""
    global _service_status
    services = [s for s in unrealsdk.find_all('SparkServiceConfiguration')
                if s._path_name().startswith('Transient.') and s.ServiceName.lower() == 'micropatch']
    if len(services) != 1:
        _service_status = dict(status='pending', detail=f'Expected one Micropatch service, found {len(services)}')
        return
    service = services[0]
    old_keys, old_values = list(service.Keys), list(service.Values)
    if len(old_keys) != len(old_values):
        _service_status = dict(status='error', detail='Existing Keys/Values lengths differ')
        return
    keys, values = old_keys.copy(), old_values.copy()
    for record in RECORDS:
        key = record['hotfix']
        if key is None:
            continue
        if key in keys:
            if keys.count(key) != 1 or values[keys.index(key)] != record['hotfix_value']:
                _service_status = dict(status='error', detail='Conflicting hotfix key: ' + key)
                return
        else:
            keys.append(key)
            values.append(record['hotfix_value'])
    if keys != old_keys:
        try:
            service.Values = values
            service.Keys = keys
            if list(service.Keys) != keys or list(service.Values) != values:
                raise RuntimeError('Hotfix service readback mismatch')
        except Exception:
            service.Values = old_values
            service.Keys = old_keys
            raise
    _service_status = dict(status='registered', path=service._path_name(), count=13,
                           total_entries=len(keys), verified_pairs=True)


def resolve(target):
    try:
        cls = unrealsdk.find_class(target)
    except ValueError:
        return [unrealsdk.find_object('Object', target)]
    return list(unrealsdk.find_all(cls, False))


def controller():
    players = ENGINE.GamePlayers
    if not players or players[0] is None:
        return None
    pc = players[0].Actor
    if pc is None or pc.WorldInfo is None or int(pc.WorldInfo.NetMode) == 3:
        return None
    return pc


def snapshot(pc):
    global _last_report
    core = {}
    for cls, props in {
        'WillowCoopGameInfo': ('MaxPlayers', 'MaxPlayersAllowed', 'EffectiveNumPlayers', 'NumPlayers'),
        'WillowOnlineGameSettings': ('NumPublicConnections', 'NumOpenPublicConnections'),
    }.items():
        core[cls] = [dict(path=o._path_name(), **{p: getattr(o, p) for p in props})
                     for o in unrealsdk.find_all(cls, False)]
    report = dict(version=__version__, world=pc.WorldInfo._path_name(), map=pc.WorldInfo.GetMapName(True), net_mode=int(pc.WorldInfo.NetMode),
                  source_sha256=SOURCE_SHA256, pick_team_calls=_pick_calls,
                  hotfix_service=_service_status, core=core, records=list(_rows.values()),
                  caveat='Pending targets are not applied. Readback is not a 5+ multiplayer test.')
    serialized = json.dumps(report, indent=2)
    if serialized == _last_report:
        return
    dest = SETTINGS_DIR / 'unlimited_coop.runtime.json'
    temp = dest.with_suffix('.tmp')
    temp.write_text(serialized, encoding='utf8')
    temp.replace(dest)
    _last_report = serialized


def apply_patch():
    global _last_summary, _last_service_status, _service_status
    pc = controller()
    if pc is None:
        return
    try:
        register_hotfixes()
    except Exception as exc:
        _service_status = dict(status='error', detail=str(exc))
    service_summary = tuple(sorted(_service_status.items()))
    if service_summary != _last_service_status:
        logging.info(f'Unlimited COOP hotfix service: {_service_status}')
        _last_service_status = service_summary
    for index, record in enumerate(RECORDS):
        target, prop, value = record['target'], record['prop'], record['value']
        row = dict(target=target, prop=prop, hotfix=record['hotfix'])
        try:
            objects = resolve(target)
            if not objects:
                raise ValueError('No loaded instances')
            # Do not retain UObject references across map unload/GC.
            identities = tuple((o._path_name(), o._get_address(), o.InternalIndex) for o in objects)
            if _seen.get(index) != identities:
                for obj in objects:
                    getattr(obj, prop)  # validate the property before invoking the engine parser
                result = pc.ConsoleCommand(COMMANDS[index], False)
                if result and any(s in result.lower() for s in ('unrecognized', 'error', 'failed')):
                    raise RuntimeError(result)
                _seen[index] = identities
            readback = [str(getattr(o, prop)) for o in objects]
            # Verify scalar commands exactly (floats with normal serialization tolerance).
            if not value.startswith('('):
                for actual in readback:
                    try:
                        same = abs(float(actual) - float(value)) < 0.0001
                    except ValueError:
                        same = actual.lower() == value.lower()
                    if not same:
                        raise RuntimeError(f'Readback differs: {actual!r} != {value!r}')
            row.update(status='read_back', objects=[o._path_name() for o in objects], values=readback)
        except ValueError as exc:
            row.update(status='pending', detail=str(exc))
            _seen.pop(index, None)
        except Exception as exc:
            row.update(status='error', detail=str(exc))
            _seen.pop(index, None)
        _rows[index] = row
    summary = tuple(sum(r['status'] == s for r in _rows.values()) for s in ('read_back','pending','error'))
    if summary != _last_summary:
        logging.info(f'Unlimited COOP: read back {summary[0]}/{len(RECORDS)}, pending {summary[1]}, errors {summary[2]}. Details: settings/unlimited_coop.runtime.json')
        _last_summary = summary
    snapshot(pc)


@hook('WillowGame.WillowCoopGameInfo:PickTeam')
def pick_team(obj, args, _ret, _func):
    global _pick_calls
    if int(obj.WorldInfo.NetMode) == 3:
        return None
    _pick_calls += 1
    return Block, args.Num


def invalidate(*_):
    global _next_check
    _seen.clear()
    _next_check = 0.0


@hook('Engine.GameInfo:PostCommitMapChange', Type.POST)
@hook('WillowGame.WillowGameInfo:PostBeginPlay', Type.POST)
@hook('WillowGame.FrontendGFxMovie:Start', Type.POST)
def map_ready(*_):
    invalidate()


@hook('Engine.PlayerController:PlayerTick', Type.POST)
def tick(obj, _args, _ret, _func):
    global _next_check, _world
    now = time.monotonic()
    if now < _next_check:
        return
    _next_check = now + 2.0
    pc = controller()
    if pc is None or obj != pc:
        return
    world = (pc.WorldInfo._path_name(), pc.WorldInfo._get_address(), pc.WorldInfo.GetMapName(True))
    if world != _world:
        _world = world
        _seen.clear()
    apply_patch()


mod = build_mod(cls=RestartToDisable, hooks=[pick_team, map_ready, tick], on_enable=invalidate)
