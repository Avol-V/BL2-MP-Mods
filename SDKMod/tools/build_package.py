"""Build a reproducible SDK archive; exclude settings, logs, saves, and caches."""
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile


def build(output=None):
    root = Path(__file__).resolve().parents[1]
    source = root / 'unlimited_coop'
    version = tomllib.loads((source / 'pyproject.toml').read_text(encoding='utf8'))['project']['version']
    output = Path(output) if output is not None else root / 'dist'
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'unlimited_coop-{version}.sdkmod'
    files = {f'unlimited_coop/{name}': (source / name).read_bytes()
             for name in ('__init__.py', 'pyproject.toml', 'cooppatch.txt', 'LICENSE')}
    with zipfile.ZipFile(archive, 'w') as package:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, data)
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None or set(package.namelist()) != set(files):
            raise ValueError('Invalid package contents')
        for name, data in files.items():
            if package.read(name) != data:
                raise ValueError('Package verification failed: ' + name)
    manifest = dict(archive=archive.name, version=version,
                    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                    files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
                    runtime_tested_format='folder; packed archive not yet tested in-game')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    return manifest


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
