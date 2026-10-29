#!/usr/bin/env python3
"""Package and verify an immutable release archive and its bundle reference."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import zipfile
from audit import audit

REPOSITORY = 'https://github.com/petitstrawberry/scarlet-bundle-lwjgl'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(root, receipt):
    files = {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*') if p.is_file()}
    if any(p.is_symlink() for p in root.rglob('*')) or files != receipt['files']:
        raise ValueError('Release payload differs from the build receipt')
    core = root / 'usr/lib/lwjgl' / receipt['version']
    if audit(core / 'liblwjgl.so') != receipt['elf']:
        raise ValueError('ELF audit changed')
    with zipfile.ZipFile(core / 'lwjgl.jar') as jar:
        for name in ('org/lwjgl/system/scarlet/ScarletLibrary.class', 'org/lwjgl/system/MemoryUtil.class', 'org/lwjgl/system/JNI.class'):
            if name not in jar.namelist(): raise ValueError('Missing core class: ' + name)

def package(build_receipt, version, output):
    if not re.fullmatch(r'v[0-9]+(?:\.[0-9]+){2}', version): raise ValueError('Expected vX.Y.Z release version')
    receipt = json.loads(build_receipt.read_text())
    if receipt['local_source'] or receipt['producer_dirty']:
        raise ValueError('Release requires pinned sources and a clean producer commit')
    root = Path(receipt['image']); verify(root, receipt)
    output.mkdir(parents=True, exist_ok=False)
    name = 'lwjgl-' + receipt['version'] + '-aarch64-' + version
    archive = output / (name + '.tar.gz')
    with archive.open('wb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            for path in sorted(root.rglob('*')):
                info = tar.gettarinfo(str(path), arcname=name + '/' + path.relative_to(root).as_posix())
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                if path.is_file():
                    with path.open('rb') as payload: tar.addfile(info, payload)
                else: tar.addfile(info)
    with tempfile.TemporaryDirectory(prefix='lwjgl-release-') as temporary:
        stage = Path(temporary)
        with tarfile.open(archive) as tar: tar.extractall(stage, filter='data')
        verify(stage / name, receipt)
    digest = sha(archive)
    url = REPOSITORY + '/releases/download/' + version + '/' + archive.name
    manifest = ('# Generated from the verified CI release archive.\n[[layers]]\nkind = "archive"\n'
                f'url = "{url}"\nsha256 = "sha256:{digest}"\nformat = "tar-gz"\nstrip_components = 1\nto = "/"\n')
    (output / 'bundle.toml').write_text(manifest)
    shutil.copyfile(build_receipt, output / 'build.json')
    (output / 'sources.json').write_text(json.dumps(receipt['sources'], indent=2) + '\n')
    release = {'version': version, 'lwjgl_version': receipt['version'], 'archive': archive.name,
               'url': url, 'sha256': digest, 'producer_revision': receipt['producer_revision']}
    (output / 'release.json').write_text(json.dumps(release, indent=2) + '\n')
    (output / 'SHA256SUMS').write_text(''.join(sha(p) + '  ' + p.name + '\n' for p in sorted(output.iterdir()) if p.is_file()))
    print(archive)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', required=True, type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    package(args.build_receipt, args.version, args.output)
