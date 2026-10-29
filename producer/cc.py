#!/usr/bin/env python3
"""Cross-compile C configure probes with the pinned Scarlet SDK."""
import os
from pathlib import Path
import subprocess
import sys

args = sys.argv[1:]
cc = os.environ['SCARLET_NATIVE_CC']
runtime = Path(os.environ['SCARLET_NATIVE_RUNTIME'])
resource = subprocess.check_output([cc, '-print-resource-dir'], text=True).strip()
flags = ['--target=aarch64-unknown-none-elf', '-nostdinc', '-isystem', resource + '/include',
         '-isystem', str(runtime / 'include'), '-D__scarlet__=1', '-fno-stack-protector',
         '-mno-outline-atomics']
link = not any(x in args for x in ('-c', '-S', '-E', '--version', '-v', '-dumpmachine', '-print-search-dirs'))
if link:
    root = Path(subprocess.check_output([os.environ['SCARLET_RUSTC'], '--print', 'sysroot'], text=True).strip())
    flags += ['-nostdlib', '-fuse-ld=lld', '-static', '-Wl,--gc-sections', '-Wl,--wrap=main',
              '-Wl,--undefined=__wrap_main', '-Wl,-z,max-page-size=4096',
              str(root / 'lib/rustlib/aarch64-unknown-scarlet/lib/scarlet-crt0.o')]
    args = [x for x in args if x not in ('-lm', '-lpthread', '-lc', '-ldl')]
    args += ['-Wl,--start-group'] + [str(runtime / 'lib' / name) for name in
             ('libc++.a', 'libc++abi.a', 'libscarlet_c_startup.a', 'libscarlet_cxx_support.a', 'libscarlet_c.a')] + ['-Wl,--end-group']
env = os.environ.copy()
for name in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH', 'LIBRARY_PATH'):
    env.pop(name, None)
subprocess.run([cc, *flags, *args], check=True, env=env)
if link:
    output = Path(args[args.index('-o') + 1]) if '-o' in args else Path('a.out')
    with output.open('r+b') as stream:
        if stream.read(4) != b'\x7fELF':
            raise ValueError('Expected target ELF executable')
        stream.seek(7)
        stream.write(b'\x53')
