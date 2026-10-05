"""Install only this SDK mod, with a dry run, verified backups, and conflict-safe rollback.

Requires Python 3.11+. Does not install the SDK or modify game binaries or saves.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

SOURCE = Path(__file__).resolve().parents[1] / 'unlimited_coop'
CORE = {
    'Binaries/Win32/Borderlands2.exe': '1231b384aea791bc51286664627d03e27d6a77ffd4ec3bb5001186c136504c17',
    'WillowGame/CookedPCConsole/WillowGame.upk': '67b7d72892275b5e95a150f4ec581c8efbc84c8cda7da82338de07cd9fef4e6d',
    'WillowGame/CookedPCConsole/Engine.upk': 'd3debcd4236dfe4084fd3d1950651f32aed4aeebf486f38f7434af3fdecb1253',
}
MOD_FILES = ('__init__.py', 'pyproject.toml', 'cooppatch.txt', 'LICENSE')
SETTINGS = 'sdk_mods/settings/unlimited_coop.json'
ALLOWED = {f'sdk_mods/unlimited_coop/{name}' for name in MOD_FILES} | {SETTINGS}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(root, relative):
    root = root.resolve()
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ValueError('Path escapes its root: ' + str(relative))
    cursor = path
    while cursor != root:
        if cursor.is_symlink() or (cursor.exists() and getattr(cursor.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Child symlink/reparse point: ' + str(cursor))
        cursor = cursor.parent
    return path


def validate_game(root, allow_untested=False):
    mismatches = []
    for relative, expected in CORE.items():
        path = checked(root, relative)
        if not path.is_file():
            raise ValueError('Not a complete Borderlands 2 installation: ' + relative)
        if sha(path.read_bytes()) != expected:
            mismatches.append(relative)
    if mismatches and not allow_untested:
        raise ValueError('Untested/modified game files: ' + ', '.join(mismatches) +
                         '. Inspect the build, or explicitly use --allow-untested-build.')
    for relative in ('Binaries/Win32/ddraw.dll', 'Binaries/Win32/Plugins/unrealsdk.dll',
                     'Binaries/Win32/Plugins/pyunrealsdk.dll', 'sdk_mods'):
        if not checked(root, relative).exists():
            raise ValueError('Install the willow2 PythonSDK mod manager first: missing ' + relative)
    packed = list(checked(root, 'sdk_mods').glob('unlimited_coop*.sdkmod'))
    if packed:
        raise ValueError('Remove the existing packed Unlimited COOP mod before installing the folder: ' + str(packed))
    return mismatches


def require_closed_game():
    if os.name == 'nt':
        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Borderlands2.exe', '/FO', 'CSV', '/NH'],
                                capture_output=True, check=True)
        if b'borderlands2.exe' in result.stdout.lower():
            raise ValueError('Close all Borderlands 2 instances before changing mod files.')


def payload(root, enable=False):
    result = {f'sdk_mods/unlimited_coop/{name}': (SOURCE / name).read_bytes() for name in MOD_FILES}
    if enable:
        path = checked(root, SETTINGS)
        previous = path.read_bytes() if path.exists() else None
        settings = json.loads(previous) if previous is not None else {}
        if not isinstance(settings, dict):
            raise ValueError('Mod settings must be a JSON object.')
        if settings.get('enabled') is True:
            result[SETTINGS] = previous
        else:
            settings['enabled'] = True
            result[SETTINGS] = (json.dumps(settings, indent=2) + '\n').encode('utf8')
    return result


def plan(root, contents):
    rows = []
    for relative, data in contents.items():
        if relative not in ALLOWED:
            raise ValueError('Not an owned mod file: ' + relative)
        path = checked(root, relative)
        before = sha(path.read_bytes()) if path.exists() else None
        if before != sha(data):
            rows.append(dict(path=relative, before=before, after=sha(data)))
    return rows


def write_verified(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.coop-tmp')
    # Never replace someone else's temporary file or follow a link.
    with temp.open('xb') as stream:
        stream.write(data)
    temp.replace(path)
    if sha(path.read_bytes()) != sha(data):
        raise ValueError('Write verification failed: ' + str(path))


def install(root, contents, backup):
    rows = plan(root, contents)
    if not rows:
        return None
    backup = backup.resolve()
    if backup.is_relative_to(root / 'sdk_mods') or backup == root or root.is_relative_to(backup):
        raise ValueError('Backups must not overlap the mod files or contain the game root.')
    backup.mkdir(parents=True, exist_ok=False)
    for row in rows:
        if row['before'] is not None:
            data = checked(root, row['path']).read_bytes()
            if sha(data) != row['before']:
                raise ValueError('Changed while preparing backup: ' + row['path'])
            write_verified(checked(backup, row['path']), data)
    manifest = dict(root=str(root), files=rows, format=1)
    write_verified(backup / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode('utf8'))
    for row in rows:
        path = checked(root, row['path'])
        current = sha(path.read_bytes()) if path.exists() else None
        if current != row['before']:
            raise ValueError('Changed before deployment: ' + row['path'])
        write_verified(path, contents[row['path']])
    return backup


def restore_plan(root, backup):
    manifest = json.loads(checked(backup, 'manifest.json').read_text(encoding='utf8'))
    if manifest.get('format') != 1 or manifest['root'] != str(root):
        raise ValueError('Unsupported manifest or wrong rollback target.')
    rows = manifest['files']
    if len({row['path'] for row in rows}) != len(rows):
        raise ValueError('Duplicate rollback paths.')
    for row in rows:
        if row['path'] not in ALLOWED:
            raise ValueError('Not an owned mod file: ' + row['path'])
        path = checked(root, row['path'])
        if not path.is_file() or sha(path.read_bytes()) != row['after']:
            raise ValueError('Changed since deployment: ' + row['path'])
        if row['before'] is not None and sha(checked(backup, row['path']).read_bytes()) != row['before']:
            raise ValueError('Backup checksum mismatch: ' + row['path'])
    return rows


def rollback(root, backup):
    rows = restore_plan(root, backup)  # Validate every file before changing any.
    for row in rows:
        path = checked(root, row['path'])
        if row['before'] is None:
            path.unlink()
        else:
            write_verified(path, checked(backup, row['path']).read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, required=True, help='Directory containing Binaries and WillowGame')
    parser.add_argument('--apply', action='store_true', help='Apply the printed plan; otherwise read-only')
    parser.add_argument('--enable', action='store_true', help='Enable the host-only mod while preserving other settings')
    parser.add_argument('--allow-untested-build', action='store_true', help='Explicitly accept untested game hashes')
    parser.add_argument('--backup-dir', type=Path, help='New backup directory; defaults inside the game root')
    parser.add_argument('--rollback', type=Path, help='Restore a backup made by this installer')
    args = parser.parse_args()
    root = args.game_dir.resolve()
    if args.rollback:
        backup = args.rollback.resolve()
        rows = restore_plan(root, backup)
    else:
        mismatches = validate_game(root, args.allow_untested_build)
        contents = payload(root, args.enable)
        rows = plan(root, contents)
        if mismatches:
            print('WARNING: build compatibility is unverified: ' + ', '.join(mismatches))
    print(json.dumps(dict(game_directory=str(root), changes=rows, apply=args.apply), indent=2))
    if not args.apply or not rows:
        return
    require_closed_game()
    if args.rollback:
        rollback(root, backup)
        print('Restored owned mod files. Restart the game to remove runtime changes.')
    else:
        backup = args.backup_dir or root / 'unlimited-coop-backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        print('Verified backup: ' + str(install(root, contents, backup)))
        print('Installed. Enable Unlimited COOP in Mods if --enable was not used.')


if __name__ == '__main__':
    main()
