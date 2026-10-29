#!/usr/bin/env python3
"""Reject native libraries that the Scarlet loader cannot load."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

# Verified against the loader-linked OpenJDK 25 runtime. New imports require
# runtime verification rather than being silently added during packaging.
IMPORTS = {
    '__errno_location', 'abort', 'calloc', 'dlclose', 'dlerror', 'dlopen', 'dlsym',
    'exit', 'fflush', 'free', 'fwrite', 'getenv', 'malloc', 'mmap', 'munmap',
    'posix_memalign', 'pthread_getspecific', 'pthread_key_create', 'pthread_key_delete',
    'pthread_setspecific', 'realloc', 'setlocale', 'snprintf', 'stderr', 'strerror', 'sysconf',
}

def audit(path):
    data = Path(path).read_bytes()
    if data[:8] != b'\x7fELF\x02\x01\x01\x53':
        raise ValueError('Expected native Scarlet ELF64 little endian')
    kind, machine = struct.unpack_from('<HH', data, 16)
    if (kind, machine) != (3, 183): raise ValueError('Expected AArch64 shared object')
    headers = subprocess.check_output(['llvm-readelf', '-W', '-l', '-d', '-r', str(path)], text=True)
    if re.search(r'^\s*(INTERP|TLS)\s', headers, re.M):
        raise ValueError('Library must not contain an interpreter or DSO TLS')
    for name in ('NEEDED', 'RPATH', 'RUNPATH', 'TEXTREL', 'RELR', 'RELRSZ', 'RELRENT', 'VERNEED', 'VERDEF', 'VERSYM', 'SYMBOLIC'):
        if '(' + name + ')' in headers: raise ValueError('Unsupported dynamic entry: ' + name)
    for flags in re.findall(r'\(FLAGS(?:_1)?\)\s+(.*)', headers):
        if flags.strip() not in ('BIND_NOW', 'NOW'): raise ValueError('Unsupported dynamic flags: ' + flags)
    relocations = sorted(set(re.findall(r'R_AARCH64_([A-Z0-9_]+)', headers)))
    if set(relocations) - {'RELATIVE', 'GLOB_DAT', 'JUMP_SLOT', 'ABS64'}:
        raise ValueError('Unsupported relocations: ' + ','.join(relocations))
    symbols = subprocess.check_output(['llvm-nm', '--dynamic', '--undefined-only', str(path)], text=True)
    imports = sorted({line.split()[-1] for line in symbols.splitlines() if line.strip()})
    if set(imports) - IMPORTS: raise ValueError('Unverified runtime imports: ' + str(sorted(set(imports) - IMPORTS)))
    definitions = subprocess.check_output(['llvm-nm', '--dynamic', '--defined-only', str(path)], text=True)
    exports = {line.split()[-1] for line in definitions.splitlines() if line.strip()}
    if 'JNI_OnLoad' not in exports or not any(s.startswith('Java_org_lwjgl_system_JNI_') for s in exports):
        raise ValueError('Missing LWJGL JNI exports')
    if any(s.startswith('ffi_') for s in exports): raise ValueError('Private libffi symbols must not interpose on the JVM')
    return {'architecture': 'aarch64', 'osabi': '0x53', 'imports': imports,
            'relocations': relocations, 'jni_exports': sum(s.startswith('Java_') for s in exports)}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('library', type=Path)
    print(json.dumps(audit(p.parse_args().library), indent=2))
