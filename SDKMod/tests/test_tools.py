"""Offline installer/rollback and archive tests with disposable files only."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load('install')
builder = load('build_package')


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'game with spaces'
        self.root.mkdir()
        self.backup = Path(self.temp.name) / 'backup'
        self.target = self.root / 'sdk_mods/unlimited_coop/__init__.py'
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'previous mod')
        self.data = {'sdk_mods/unlimited_coop/__init__.py': b'updated mod',
                     'sdk_mods/unlimited_coop/LICENSE': b'license'}

    def test_dry_plan_is_read_only(self):
        self.assertEqual(len(installer.plan(self.root, self.data)), 2)
        self.assertEqual(self.target.read_bytes(), b'previous mod')
        self.assertFalse(self.backup.exists())

    def test_install_idempotence_and_exact_rollback(self):
        installer.install(self.root, self.data, self.backup)
        self.assertEqual(installer.plan(self.root, self.data), [])
        installer.rollback(self.root, self.backup)
        self.assertEqual(self.target.read_bytes(), b'previous mod')
        self.assertFalse((self.root / 'sdk_mods/unlimited_coop/LICENSE').exists())

    def test_conflict_prevents_all_rollback_writes(self):
        installer.install(self.root, self.data, self.backup)
        self.target.write_bytes(b'user change')
        with self.assertRaises(ValueError):
            installer.rollback(self.root, self.backup)
        self.assertEqual(self.target.read_bytes(), b'user change')
        self.assertTrue((self.root / 'sdk_mods/unlimited_coop/LICENSE').exists())

    def test_tampered_backup_rejected(self):
        installer.install(self.root, self.data, self.backup)
        (self.backup / 'sdk_mods/unlimited_coop/__init__.py').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            installer.rollback(self.root, self.backup)
        self.assertEqual(self.target.read_bytes(), b'updated mod')

    def test_settings_preserve_other_values_and_format(self):
        path = self.root / installer.SETTINGS
        path.parent.mkdir(parents=True)
        path.write_text('{"enabled": false, "other": 17}')
        data = installer.payload(self.root, enable=True)
        self.assertEqual(json.loads(data[installer.SETTINGS]), {'enabled': True, 'other': 17})
        path.write_bytes(data[installer.SETTINGS])
        self.assertEqual(installer.payload(self.root, True)[installer.SETTINGS], path.read_bytes())

    def test_escape_and_unknown_owned_file_rejected(self):
        with self.assertRaises(ValueError):
            installer.checked(self.root, '../outside')
        with self.assertRaises(ValueError):
            installer.plan(self.root, {'Binaries/Win32/Borderlands2.exe': b'no'})

    def test_backup_overlap_rejected(self):
        with self.assertRaises(ValueError):
            installer.install(self.root, self.data, self.root / 'sdk_mods/backup')

    def test_duplicate_rollback_paths_rejected(self):
        installer.install(self.root, self.data, self.backup)
        path = self.backup / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['files'].append(manifest['files'][0])
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            installer.rollback(self.root, self.backup)

    def test_game_validation_requires_explicit_override_and_sdk(self):
        relative = 'Binaries/Win32/Borderlands2.exe'
        path = self.root / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(b'untested fixture')
        with patch.object(installer, 'CORE', {relative: installer.sha(b'tested fixture')}):
            with self.assertRaises(ValueError):
                installer.validate_game(self.root)
            with self.assertRaises(ValueError):
                installer.validate_game(self.root, True)  # Missing SDK still rejected.
            for name in ('Binaries/Win32/ddraw.dll', 'Binaries/Win32/Plugins/unrealsdk.dll',
                         'Binaries/Win32/Plugins/pyunrealsdk.dll'):
                component = self.root / name
                component.parent.mkdir(parents=True, exist_ok=True)
                component.write_bytes(b'fixture')
            self.assertEqual(installer.validate_game(self.root, True), [relative])
            for name in ('unlimited_coop-1.1.0.sdkmod', 'unlimited_coop.sdkmod'):
                packed = self.root / 'sdk_mods' / name
                packed.write_bytes(b'duplicate')
                with self.assertRaises(ValueError):
                    installer.validate_game(self.root, True)
                packed.unlink()


class PackageTests(unittest.TestCase):
    def test_archive_is_reproducible_and_contains_only_source(self):
        with tempfile.TemporaryDirectory() as output:
            first = builder.build(output)
            second = builder.build(output)
            self.assertEqual(first['sha256'], second['sha256'])
            with zipfile.ZipFile(Path(output) / first['archive']) as archive:
                self.assertEqual(set(archive.namelist()), {f'unlimited_coop/{name}' for name in installer.MOD_FILES})

    def test_archive_name_matches_its_single_root_folder(self):
        # The SDK mod manager (sdk_mods/__main__.py, validate_file_in_mods_folder) ignores a .sdkmod
        # unless it holds exactly one root entry named like the archive without its extension.
        with tempfile.TemporaryDirectory() as output:
            path = Path(output) / builder.build(output)['archive']
            # Close the archive before cleanup: Windows cannot delete a file that is still open.
            with zipfile.ZipFile(path) as archive:
                roots = list(zipfile.Path(archive).iterdir())
                self.assertEqual([root.name for root in roots], [path.stem])
                self.assertTrue(roots[0].is_dir())


if __name__ == '__main__':
    unittest.main()
