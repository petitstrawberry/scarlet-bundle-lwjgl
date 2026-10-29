#!/usr/bin/env python3
"""Publish a new verified CI archive, then update its bundle pin."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts', type=Path, required=True)
    a = p.parse_args()
    directory = a.artifacts.resolve()
    release = json.loads((directory / 'release.json').read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if release['producer_revision'] != revision:
        raise ValueError('Release producer revision does not match checkout')
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        if Path(name).name != name or hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Invalid release inventory: ' + name)
    version = release['version']
    if not re.fullmatch(r'v\d+\.\d+\.\d+', version): raise ValueError('Invalid release version')
    # The archive is already audited by the producer job. Never replace an asset.
    subprocess.run(['gh', 'release', 'create', version, '--repo', 'petitstrawberry/scarlet-bundle-lwjgl',
                    '--target', revision, '--title', 'LWJGL ' + release['lwjgl_version'] + ' for Scarlet ' + version,
                    '--prerelease', '--notes', 'Native Scarlet AArch64 LWJGL core. See the README for runtime requirements and supported APIs.',
                    *[str(p) for p in sorted(directory.iterdir()) if p.is_file()]], check=True)
    with urllib.request.urlopen(release['url'], timeout=90) as response:
        digest = hashlib.file_digest(response, 'sha256').hexdigest()
    if digest != release['sha256']: raise ValueError('Published archive checksum mismatch')
    bundle = ROOT / 'bundles' / ('lwjgl-' + release['lwjgl_version']) / 'bundle.toml'
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_bytes((directory / 'bundle.toml').read_bytes())
    subprocess.run(['git', 'add', str(bundle)], cwd=ROOT, check=True)
    subprocess.run(['git', 'commit', '-m', 'Pin LWJGL CI archive ' + version], cwd=ROOT, check=True)
    subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=ROOT, check=True)

if __name__ == '__main__': main()
