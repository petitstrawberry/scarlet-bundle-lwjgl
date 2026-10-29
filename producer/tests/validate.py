#!/usr/bin/env python3
"""Run the native LWJGL core smoke test in an isolated Scarlet HVF guest."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def archive(entries, target):
    with target.open('wb') as output:
        for index, (name, mode, data) in enumerate([*entries, ('TRAILER!!!', 0, b'')], 1):
            encoded = name.encode() + b'\0'
            fields = [index, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
            header = b'070701' + ''.join(f'{value:08x}' for value in fields).encode()
            output.write(header + encoded)
            output.write(b'\0' * (-(len(header) + len(encoded)) % 4))
            output.write(data)
            output.write(b'\0' * (-len(data) % 4))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('kernel', 'init', 'loader', 'java', 'java-home', 'core', 'output'):
        p.add_argument('--' + name, required=True, type=Path)
    p.add_argument('--qemu', required=True)
    p.add_argument('--timeout', type=int, default=240)
    a = p.parse_args()
    out = a.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env['LC_ALL'] = 'C'
    def run(command, name):
        with (out / name).open('w') as log:
            subprocess.run([str(x) for x in command], check=True, env=env,
                           stdout=log, stderr=subprocess.STDOUT)
    run([Path(env['JAVA_HOME']) / 'bin/javac', '-encoding', 'UTF-8', '-cp', a.core / 'lwjgl.jar',
         '-d', out / 'classes', HERE / 'LwjglSmoke.java'], 'javac.log')
    run([env['SCARLET_RUSTC'], '--edition=2024', '--target=aarch64-unknown-scarlet', '-C', 'panic=abort',
         '-C', 'target-feature=+crt-static', '-C', 'relocation-model=static',
         '-C', 'link-arg=--no-dynamic-linker', '-O', HERE / 'supervisor.rs', '-o', out / 'supervisor'], 'rustc.log')
    cc = env['SCARLET_NATIVE_CC']
    resource = subprocess.check_output([cc, '-print-resource-dir'], text=True).strip()
    run([cc, '--target=aarch64-unknown-none-elf', '-O2', '-fPIC', '-nostdinc', '-nostdlib',
         '-isystem', resource + '/include', '-isystem', Path(env['SCARLET_NATIVE_RUNTIME']) / 'include',
         '-fuse-ld=lld', '-Wl,-shared', '-Wl,-Bdynamic', '-Wl,-z,max-page-size=4096',
         '-Wl,--hash-style=both', HERE / 'probe.c', '-o', out / 'liblwjgl_probe.so'], 'probe.log')
    with (out / 'liblwjgl_probe.so').open('r+b') as stream:
        stream.seek(7); stream.write(b'\x53')
    entries = {name: (0o40755, b'') for name in ('bin', 'dev', 'etc', 'tmp', 'root', 'mnt', 'mnt/newroot')}
    inputs = {}
    def add(path, name, executable=False):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Expected regular input: ' + str(path))
        for parent in Path(name).parents:
            if str(parent) != '.': entries[parent.as_posix()] = (0o40755, b'')
        entries[name] = (0o100755 if executable else 0o100644, path.read_bytes())
        inputs[name] = sha(path)
    add(a.init, 'init', True)
    add(a.java, 'bin/java', True)
    add(a.loader, 'bin/scarlet-ld', True)
    add(out / 'supervisor', 'bin/lwjgl-test', True)
    add(a.core / 'lwjgl.jar', 'app/lwjgl.jar')
    add(a.core / 'liblwjgl.so', 'app/native/liblwjgl.so')
    add(out / 'liblwjgl_probe.so', 'app/native/liblwjgl_probe.so')
    for base, dest in ((a.java_home, 'usr/lib/jvm/' + a.java_home.name), (out / 'classes', 'app/classes')):
        for path in sorted(base.rglob('*')):
            if path.is_file(): add(path, dest + '/' + path.relative_to(base).as_posix())
    initrd = out / 'initramfs.cpio'
    archive([(n, *v) for n, v in sorted(entries.items())], initrd)
    command = [a.qemu, '-machine', 'virt,gic-version=3', '-accel', 'hvf', '-cpu', 'host',
               '-m', '1G', '-smp', '4', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
               '-no-reboot', '-kernel', str(a.kernel), '-initrd', str(initrd),
               '-append', 'console=ttyAMA0 init.exec=/bin/lwjgl-test']
    timed_out = False
    with (out / 'qemu.log').open('w') as stream:
        try:
            status = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=a.timeout).returncode
        except subprocess.TimeoutExpired:
            timed_out, status = True, None
    log = (out / 'qemu.log').read_text(errors='replace')
    compiled = all(re.search(r'\d+\s+\d+\s+[! ]*b\s+4\s+' + re.escape(name) + r' \(\d+ bytes\)', log)
                   for name in ('LwjglSmoke::memory', 'LwjglSmoke$DoubleCallback::callback'))
    passed = (compiled and status == 0 and not timed_out and log.count('LWJGL_TEST PASS') == 2
              and 'LWJGL_GUEST -Xint exit=0' in log and 'LWJGL_GUEST -Xcomp exit=0' in log
              and 'LWJGL_GUEST FAIL' not in log and 'LWJGL_GUEST PASS' in log)
    result = {'result': 'PASS' if passed else 'FAIL', 'command': command,
              'kernel_sha256': sha(a.kernel), 'inputs': inputs, 'log_sha256': sha(out / 'qemu.log'),
              'c2_memory_and_callback': compiled, 'timed_out': timed_out, 'qemu_exit': status}
    (out / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['result'], out / 'validation.json')
    if not passed: raise SystemExit(1)

if __name__ == '__main__': main()
