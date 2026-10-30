#!/usr/bin/env python3
"""Build pinned LWJGL core/GLFW/Vulkan modules and Scarlet native libraries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
from audit import audit
from graphics import build_graphics
from applications import build_applications

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / 'producer/cache'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def download(spec, name):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        temporary = path.with_suffix(path.suffix + '.part')
        with urllib.request.urlopen(spec['url'], timeout=90) as response, temporary.open('wb') as stream:
            shutil.copyfileobj(response, stream)
        if sha(temporary) != spec['sha256']:
            temporary.unlink()
            raise ValueError('Download checksum mismatch: ' + name)
        temporary.rename(path)
    if path.is_symlink() or sha(path) != spec['sha256']:
        raise ValueError('Cache checksum mismatch: ' + name)
    return path

def extract(archive, destination):
    destination.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(destination, filter='data')
    roots = list(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError('Expected one source directory')
    return roots[0]

def run(command, cwd, log, env):
    with log.open('w') as stream:
        subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True,
                       stdout=stream, stderr=subprocess.STDOUT)

def build(args):
    spec = json.loads((ROOT / 'versions' / args.version / 'sources.json').read_text())
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    logs = out / 'logs'; logs.mkdir()
    env = dict(os.environ, LC_ALL='C')
    for name in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH', 'LIBRARY_PATH'):
        env.pop(name, None)
    source = args.source.resolve() if args.source else extract(
        download(spec['lwjgl'], spec['lwjgl']['commit'] + '.tar.gz'), out / 'lwjgl-source')
    glfw = args.glfw_source.resolve() if args.glfw_source else extract(download(spec['glfw'], spec['glfw']['commit'] + '.tar.gz'), out / 'glfw-source')
    scarlet = args.scarlet_source.resolve() if args.scarlet_source else extract(download(spec['scarlet'], spec['scarlet']['commit'] + '.tar.gz'), out / 'scarlet-source')
    scarlet_ui = args.scarlet_ui_source.resolve() if args.scarlet_ui_source else extract(download(spec['scarlet_ui'], spec['scarlet_ui']['commit'] + '.tar.gz'), out / 'scarlet-ui-source')
    core = source / 'modules/lwjgl/core/src'
    for name, header in spec['jni_headers'].items(): download(header, name)
    annotations = download(spec['jspecify'], 'jspecify-1.0.0.jar')
    ffi = extract(download(spec['libffi'], 'libffi-3.8.0.tar.gz'), out / 'ffi-source')
    ffi_build = out / 'ffi-build'; ffi_build.mkdir()
    run(['bash', ffi / 'configure', '--host=aarch64-unknown-none', '--disable-shared',
         '--disable-docs', '--disable-multi-os-directory', '--disable-exec-static-tramp',
         'CC=' + str(ROOT / 'producer/cc.py'), 'AR=' + env['SCARLET_NATIVE_AR'],
         'RANLIB=' + env['SCARLET_NATIVE_RANLIB'], 'CFLAGS=-O2 -fPIC'],
        ffi_build, logs / 'ffi-configure.log', env)
    run(['make', '-j' + str(args.jobs)], ffi_build, logs / 'ffi-build.log', env)
    cc = env['SCARLET_NATIVE_CC']
    runtime = Path(env['SCARLET_NATIVE_RUNTIME'])
    resource = subprocess.check_output([cc, '-print-resource-dir'], text=True, env=env).strip()
    flags = ['--target=aarch64-unknown-none-elf', '-O2', '-fPIC', '-fvisibility=hidden',
             '-fno-stack-protector', '-mno-outline-atomics', '-nostdinc',
             '-isystem', resource + '/include', '-isystem', runtime / 'include',
             '-DLWJGL_SCARLET', '-DLWJGL_arm64', '-D__scarlet__=1']
    for directory in (core / 'main/c', core / 'main/c/scarlet', CACHE, ffi_build / 'include'):
        flags += ['-I', directory]
    native = sorted((core / 'main/c').glob('*.c')) + sorted((core / 'main/c/scarlet').glob('*.c'))
    native += [p for p in sorted((core / 'generated/c').glob('*.c'))
               if p.name != 'org_lwjgl_system_libc_LibCStdio.c']
    llvm = Path(env['SCARLET_LLVM_SOURCE'])
    native += [llvm / 'compiler-rt/lib/builtins/clear_cache.c']
    objects = out / 'objects'; objects.mkdir()
    def compile(path):
        obj = objects / (path.stem + '.o')
        run([cc, *flags, '-c', path, '-o', obj], out, logs / (path.stem + '.log'), env)
        return obj
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        compiled = list(pool.map(compile, native))
    rust_root = Path(subprocess.check_output([env['SCARLET_RUSTC'], '--print', 'sysroot'], text=True).strip())
    builtins = list((rust_root / 'lib/rustlib/aarch64-unknown-scarlet/lib').glob('libcompiler_builtins-*.rlib'))
    if len(builtins) != 1: raise ValueError('Expected one compiler_builtins archive')
    stage = out / 'image'
    lib = stage / 'usr/lib/lwjgl' / args.version; lib.mkdir(parents=True)
    target = lib / 'liblwjgl.so'
    run([cc, '--target=aarch64-unknown-none-elf', '-nostdlib', '-fuse-ld=lld',
         '-Wl,-shared', '-Wl,-Bdynamic', '-Wl,--exclude-libs,ALL', '-Wl,-z,max-page-size=4096',
         '-Wl,--hash-style=both', '-Wl,-soname,liblwjgl.so',
         '-Wl,--version-script=' + str(ROOT / 'producer/exports.map'),
         *compiled, ffi_build / '.libs/libffi.a', builtins[0], '-o', target], out, logs / 'link.log', env)
    with target.open('r+b') as stream:
        if stream.read(4) != b'\x7fELF': raise ValueError('Expected ELF native library')
        stream.seek(7); stream.write(b'\x53')
    classes = out / 'classes'; classes.mkdir()
    java_sources = sorted((core / 'main/java').rglob('*.java')) + sorted((core / 'generated/java').rglob('*.java'))
    arguments = out / 'javac.args'
    arguments.write_text('\n'.join('"' + str(path) + '"' for path in java_sources))
    jdk = Path(env['JAVA_HOME'])
    run([jdk / 'bin/javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8',
         '-cp', annotations, '-d', classes, '@' + str(arguments)], out, logs / 'javac.log', env)
    manifest = out / 'MANIFEST.MF'
    manifest.write_text('Manifest-Version: 1.0\nSpecification-Version: ' + args.version + '\nImplementation-Version: scarlet\n\n')
    run([jdk / 'bin/jar', '--create', '--date=2026-08-23T00:00:00Z', '--file', lib / 'lwjgl.jar',
         '--manifest', manifest, '-C', classes, '.'], out, logs / 'jar.log', env)
    elf = audit(target)
    shutil.copyfile(annotations, lib / 'jspecify.jar')
    legal = stage / 'usr/share/licenses/lwjgl' / args.version; legal.mkdir(parents=True)
    shutil.copyfile(download(spec['jspecify_license'], 'jspecify-LICENSE'), legal / 'jspecify.txt')
    shutil.copyfile(source / 'LICENSE.md', legal / 'LWJGL.txt')
    shutil.copyfile(ffi / 'LICENSE', legal / 'libffi.txt')
    shutil.copyfile(llvm / 'compiler-rt/LICENSE.TXT', legal / 'compiler-rt.txt')
    shutil.copyfile(rust_root / 'lib/rustlib/src/rust/library/compiler-builtins/LICENSE.txt', legal / 'compiler-builtins.txt')
    shutil.copyfile(ROOT / 'LICENSE', legal / 'producer.txt')
    (legal / 'sources.json').write_text(json.dumps(spec, indent=2) + '\n')
    graphics = build_graphics(source, glfw, scarlet, scarlet_ui, out, lib, classes, builtins[0], env, run)
    applications = build_applications(source, scarlet, scarlet_ui, spec, out, lib, classes,
                                     builtins[0], env, run, download, extract, args.jobs)
    receipt = {'applications': applications, 'graphics': graphics, 'elf': elf, 'version': args.version, 'source': str(source), 'local_source': bool(args.source or args.glfw_source or args.scarlet_source or args.scarlet_ui_source),
               'image': str(stage), 'core': str(lib), 'sources': spec,
               'toolchain': {k: env[k] for k in ('SCARLET_NATIVE_CC', 'SCARLET_NATIVE_RUNTIME', 'SCARLET_LLVM_SOURCE', 'SCARLET_RUSTC', 'JAVA_HOME')},
               'producer_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'producer_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
               'files': {p.relative_to(stage).as_posix(): sha(p) for p in sorted(stage.rglob('*')) if p.is_file()}}
    (out / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(out / 'build.json')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', default='3.4.3')
    p.add_argument('--source', type=Path, help='Development checkout; not eligible for release')
    p.add_argument('--glfw-source', type=Path, help='Development GLFW checkout; not eligible for release')
    p.add_argument('--scarlet-ui-source', type=Path, help='Development ScarletUI checkout; not eligible for release')
    p.add_argument('--scarlet-source', type=Path, help='Development SWS checkout; not eligible for release')
    p.add_argument('--output', type=Path, required=True, help='New output directory')
    p.add_argument('--jobs', type=int, default=4)
    build(p.parse_args())
