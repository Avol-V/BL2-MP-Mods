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
# Record indices by target: a pass resolves each target once, not once per record.
TARGETS = {t: [i for i, r in enumerate(RECORDS) if r['target'] == t] for t in dict.fromkeys(r['target'] for r in RECORDS)}
CORE = {
    'WillowCoopGameInfo': ('MaxPlayers', 'MaxPlayersAllowed', 'EffectiveNumPlayers', 'NumPlayers'),
    'WillowOnlineGameSettings': ('NumPublicConnections', 'NumOpenPublicConnections'),
}
CHECK_INTERVAL = 2.0
# Full passes after a trigger at 0, 2, 6, 14, 30 and 62 s, then none until the next trigger.
FOLLOW_UP_MAX = 32.0
# Map hooks this close together belong to one map change: only the first forgets applied identities.
INVALIDATE_BURST = 10.0
_seen = {}
_rows = {}
_core = {}
_queue = []
_next_check = 0.0
_next_full = 0.0
_full_delay = CHECK_INTERVAL
_last_invalidate = float('-inf')
_world = None
_players = None
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
    """Write diagnostics when they change; core values come from the last full pass."""
    global _last_report
    report = dict(version=__version__, world=pc.WorldInfo._path_name(), map=pc.WorldInfo.GetMapName(True), net_mode=int(pc.WorldInfo.NetMode),
                  source_sha256=SOURCE_SHA256, pick_team_calls=_pick_calls,
                  hotfix_service=_service_status, core={cls: _core.get(cls, []) for cls in CORE},
                  records=[_rows[i] for i in sorted(_rows)],
                  caveat='Pending targets are not applied. Readback is not a 5+ multiplayer test.')
    if report == _last_report:
        return
    dest = SETTINGS_DIR / 'unlimited_coop.runtime.json'
    temp = dest.with_suffix('.tmp')
    temp.write_text(json.dumps(report, indent=2), encoding='utf8')
    temp.replace(dest)
    _last_report = report


def apply_service(_pc):
    global _last_service_status, _service_status
    try:
        register_hotfixes()
    except Exception as exc:
        _service_status = dict(status='error', detail=str(exc))
    service_summary = tuple(sorted(_service_status.items()))
    if service_summary != _last_service_status:
        logging.info(f'Unlimited COOP hotfix service: {_service_status}')
        _last_service_status = service_summary


def fail(target, status, exc):
    for index in TARGETS[target]:
        record = RECORDS[index]
        _rows[index] = dict(target=target, prop=record['prop'], hotfix=record['hotfix'], status=status, detail=str(exc))
        _seen.pop(index, None)
    _core.pop(target, None)


def apply_target(pc, target):
    """Resolve one target (a full GObjects scan for classes), then apply and read back its records."""
    try:
        objects = resolve(target)
        if not objects:
            raise ValueError('No loaded instances')
        # Do not retain UObject references across map unload/GC.
        identities = tuple((o._path_name(), o._get_address(), o.InternalIndex) for o in objects)
    except ValueError as exc:
        return fail(target, 'pending', exc)
    except Exception as exc:
        return fail(target, 'error', exc)
    for index in TARGETS[target]:
        record = RECORDS[index]
        prop, value = record['prop'], record['value']
        row = dict(target=target, prop=prop, hotfix=record['hotfix'])
        try:
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
    if target in CORE:
        _core[target] = [dict(path=o._path_name(), **{p: getattr(o, p) for p in CORE[target]}) for o in objects]


def report(pc):
    global _last_summary
    summary = tuple(sum(r['status'] == s for r in _rows.values()) for s in ('read_back','pending','error'))
    if summary != _last_summary:
        logging.info(f'Unlimited COOP: read back {summary[0]}/{len(RECORDS)}, pending {summary[1]}, errors {summary[2]}. Details: settings/unlimited_coop.runtime.json')
        _last_summary = summary
    snapshot(pc)


def pass_steps(full):
    """A full pass covers every target; otherwise only targets not yet read back (cheap object lookups)."""
    targets = [t for t, indices in TARGETS.items()
               if full or any(_rows.get(i, {}).get('status') != 'read_back' for i in indices)]
    service = full or _service_status.get('status') != 'registered'
    return ([(apply_service,)] if service else []) + [(apply_target, t) for t in targets] + [(report,)]


def run_step(pc, step):
    step[0](pc, *step[1:])


def apply_patch():
    """Run a full pass at once (diagnostic scripts); the tick hook spreads passes over frames."""
    pc = controller()
    if pc is None:
        return
    for step in pass_steps(True):
        run_step(pc, step)


def start_pass(pc):
    """Queue the next pass. Full passes only follow triggers, at growing intervals; the rest are light.

    Triggers are map changes and player-count changes. In a five-player session every readback
    error (EffectiveNumPlayers, AdjustedNetSpeed recomputed by the game) followed a join or leave.
    """
    global _next_check, _next_full, _full_delay, _world, _players
    world = (pc.WorldInfo._path_name(), pc.WorldInfo._get_address(), pc.WorldInfo.GetMapName(True))
    game = pc.WorldInfo.Game
    players = None if game is None else game.NumPlayers
    if world != _world:
        _world = world
        invalidate()
    if players != _players:  # a join or leave brings new instances and recomputed net speeds
        _players = players
        _next_full, _full_delay = 0.0, CHECK_INTERVAL
    now = time.monotonic()
    _next_check = now + CHECK_INTERVAL
    full = now >= _next_full
    if full:
        _next_full = now + _full_delay if _full_delay <= FOLLOW_UP_MAX else float('inf')
        _full_delay *= 2
    _queue[:] = pass_steps(full)


@hook('WillowGame.WillowCoopGameInfo:PickTeam')
def pick_team(obj, args, _ret, _func):
    global _pick_calls
    if int(obj.WorldInfo.NetMode) == 3:
        return None
    _pick_calls += 1
    return Block, args.Num


def invalidate(*_):
    """Restart full passes. Seamless travel fires several map hooks within seconds; forgetting
    applied identities once per burst keeps unchanged objects from being re-applied each time."""
    global _next_check, _next_full, _full_delay, _last_invalidate
    now = time.monotonic()
    if now - _last_invalidate > INVALIDATE_BURST:
        _seen.clear()
    _last_invalidate = now
    _queue.clear()
    _next_check = _next_full = 0.0
    _full_delay = CHECK_INTERVAL


@hook('Engine.GameInfo:PostCommitMapChange', Type.POST)
@hook('WillowGame.WillowGameInfo:PostBeginPlay', Type.POST)
@hook('WillowGame.FrontendGFxMovie:Start', Type.POST)
def map_ready(*_):
    invalidate()


@hook('Engine.PlayerController:PlayerTick', Type.POST)
def tick(obj, _args, _ret, _func):
    # One step per frame: a whole pass in one frame stalled the game thread for ~100 ms every 2 s.
    if not _queue and time.monotonic() < _next_check:
        return
    pc = controller()
    if pc is None or obj != pc:
        return
    if not _queue:
        start_pass(pc)
    run_step(pc, _queue.pop(0))


mod = build_mod(cls=RestartToDisable, hooks=[pick_team, map_ready, tick], on_enable=invalidate)
