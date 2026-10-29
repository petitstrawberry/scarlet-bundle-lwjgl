"""Build the GLFW native backend and LWJGL GLFW/Vulkan Java modules."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from audit import audit


def build_graphics(source, glfw, scarlet, out, lib, core_classes, builtins, env, run):
    logs = out / 'logs'
    sws_target = out / 'sws-target'
    sws_env = dict(env, CARGO_TARGET_DIR=str(sws_target))
    run(['cargo', 'build', '--locked', '--manifest-path', scarlet / 'user/lib/sws-client-c/Cargo.toml',
         '--release', '--target', 'aarch64-unknown-scarlet'], out, logs / 'sws.log', sws_env)
    sws = sws_target / 'aarch64-unknown-scarlet/release'
    cc = env['SCARLET_NATIVE_CC']
    resource = subprocess.check_output([cc, '-print-resource-dir'], text=True, env=env).strip()
    flags = ['--target=aarch64-unknown-none-elf', '-O2', '-fPIC', '-fvisibility=hidden',
             '-fno-stack-protector', '-mno-outline-atomics', '-nostdinc',
             '-isystem', resource + '/include', '-isystem', env['SCARLET_NATIVE_RUNTIME'] + '/include',
             '-I', scarlet / 'user/lib/sws-client-c/include', '-D__scarlet__=1',
             '-D_GLFW_SCARLET', '-D_GLFW_BUILD_DLL', '-D_POSIX_MONOTONIC_CLOCK=1']
    objects = out / 'glfw-objects'; objects.mkdir()
    names = ('context init input monitor platform vulkan window egl_context osmesa_context '
             'null_init null_monitor null_window null_joystick posix_time posix_module posix_thread '
             'scarlet_init scarlet_monitor scarlet_window').split()
    def compile(name):
        obj = objects / (name + '.o')
        run([cc, *flags, '-c', glfw / 'src' / (name + '.c'), '-o', obj], out, logs / ('glfw-' + name + '.log'), env)
        return obj
    with ThreadPoolExecutor(max_workers=4) as pool:
        compiled = list(pool.map(compile, names))
    exports = out / 'glfw.exports'; exports.write_text('{ global: glfw*; local: *; };\n')
    target = lib / 'libglfw.so'
    run([cc, '--target=aarch64-unknown-none-elf', '-nostdlib', '-fuse-ld=lld',
         '-Wl,-shared', '-Wl,-Bdynamic', '-Wl,--exclude-libs,ALL', '-Wl,--hash-style=both',
         '-Wl,-z,max-page-size=4096', '-Wl,-soname,libglfw.so', '-Wl,--version-script=' + str(exports),
         *compiled, builtins, '-L' + str(sws), '-lsws_client_c', '-o', target], out, logs / 'glfw-link.log', env)
    with target.open('r+b') as stream:
        stream.seek(7); stream.write(b'\x53')
    native = audit(target, 'glfw')
    jdk = Path(env['JAVA_HOME'])
    for module in ('vulkan', 'glfw'):
        root = source / 'modules/lwjgl' / module / 'src'
        sources = sorted((root / 'main/java').rglob('*.java')) + sorted((root / 'generated/java').rglob('*.java'))
        classes = out / (module + '-classes'); classes.mkdir()
        arguments = out / (module + '-javac.args')
        arguments.write_text('\n'.join('"' + str(path) + '"' for path in sources))
        run([jdk / 'bin/javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8',
             '-cp', os.pathsep.join([str(core_classes), str(out / 'vulkan-classes'), str(lib / 'jspecify.jar')]),
             '-d', classes, '@' + str(arguments)], out, logs / (module + '-javac.log'), env)
        run([jdk / 'bin/jar', '--create', '--date=2026-08-23T00:00:00Z',
             '--file', lib / ('lwjgl-' + module + '.jar'), '-C', classes, '.'], out, logs / (module + '-jar.log'), env)
    legal = out / 'image/usr/share/licenses/lwjgl' / lib.name
    shutil.copyfile(glfw / 'LICENSE.md', legal / 'GLFW.txt')
    return {'glfw': native, 'sws_runtime': {
        'path': '/lib/libsws_client_c.so',
        'link_input_sha256': hashlib.sha256((sws / 'libsws_client_c.so').read_bytes()).hexdigest(),
        'included': False,
    }}
