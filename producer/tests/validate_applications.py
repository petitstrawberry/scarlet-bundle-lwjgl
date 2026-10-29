#!/usr/bin/env python3
"""Exercise native application libraries in an isolated AArch64 HVF guest."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from validate import archive, sha

HERE = Path(__file__).resolve().parent
CASES = ('SdlLoadSmoke', 'StbSmoke', 'FreeTypeSmoke', 'ShaderSmoke', 'OpenALSmoke', 'OpenGLLoadSmoke', 'ApplicationsSmoke')
MARKERS = ('SDL_LOAD PASS', 'STB_NATIVE PASS', 'FREETYPE_NATIVE PASS', 'SHADER_NATIVE PASS',
           'OPENAL_NATIVE PASS', 'OPENGL_DISPATCH PASS', 'VMA_LOAD PASS', 'APPLICATION_MODULES PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('kernel', 'init', 'loader', 'java', 'java-home', 'core', 'font', 'sws-client', 'scarlet-ui', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--qemu', required=True)
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, LC_ALL='C')
    jars = sorted(args.core.glob('*.jar'))
    if not jars: parser.error('Expected native LWJGL module jars')
    classes = out / 'classes'
    def run(command, log):
        with (out / log).open('w') as stream:
            subprocess.run(list(map(str, command)), env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    run([Path(env['JAVA_HOME']) / 'bin/javac', '-encoding', 'UTF-8', '-cp',
         os.pathsep.join(map(str, jars)), '-d', classes, *[HERE / (name + '.java') for name in CASES]], 'javac.log')
    run([env['SCARLET_RUSTC'], '--edition=2024', '--target=aarch64-unknown-scarlet', '-C', 'panic=abort',
         '-C', 'target-feature=+crt-static', '-C', 'relocation-model=static', '-C', 'link-arg=--no-dynamic-linker',
         '-O', HERE / 'applications_supervisor.rs', '-o', out / 'supervisor'], 'rustc.log')
    entries = {name: (0o40755, b'') for name in ('bin', 'lib', 'dev', 'etc', 'tmp', 'root', 'mnt', 'mnt/newroot')}
    inputs = {}
    def add(path, name, executable=False):
        if path.is_symlink() or not path.is_file(): raise ValueError('Expected regular input: ' + str(path))
        for parent in Path(name).parents:
            if str(parent) != '.': entries[parent.as_posix()] = (0o40755, b'')
        entries[name] = (0o100755 if executable else 0o100644, path.read_bytes())
        inputs[name] = sha(path)
    for path, name in ((args.init, 'init'), (args.java, 'bin/java'), (args.loader, 'bin/scarlet-ld'),
                       (out / 'supervisor', 'bin/applications-test')):
        add(path, name, True)
    add(args.font, 'app/font.ttf')
    add(args.sws_client, 'lib/libsws_client_c.so', True)
    add(args.scarlet_ui, 'lib/libscarlet_ui_window.so', True)
    for path in jars: add(path, 'app/' + path.name)
    for path in sorted(args.core.glob('*.so*')): add(path, 'app/native/' + path.name, True)
    for base, target in ((args.java_home, 'usr/lib/jvm/' + args.java_home.name), (classes, 'app/classes')):
        for path in sorted(base.rglob('*')):
            if path.is_file(): add(path, target + '/' + path.relative_to(base).as_posix())
    arguments = ['-Xms256m', '-Xmx1g', '-Xcheck:jni', '--enable-native-access=ALL-UNNAMED',
        '-Dorg.lwjgl.librarypath=/app/native', '-Dorg.lwjgl.system.allocator=system',
        '-Dorg.lwjgl.vulkan.explicitInit=true', '-cp',
        ':'.join(['/app/' + path.name for path in jars] + ['/app/classes']), 'ApplicationsSmoke']
    entries['app/java-arguments'] = (0o100644, ('\n'.join(arguments) + '\n').encode())
    image = out / 'initramfs.cpio'; archive([(name, *value) for name, value in sorted(entries.items())], image)
    command = [args.qemu, '-machine', 'virt,gic-version=3', '-accel', 'hvf', '-cpu', 'host',
        '-m', '4G', '-smp', '4', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
        '-nic', 'none', '-no-reboot', '-kernel', str(args.kernel.resolve()), '-initrd', str(image),
        '-append', 'console=ttyAMA0 init.exec=/bin/applications-test']
    timeout = False
    with (out / 'qemu.log').open('w') as log:
        try: status = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout).returncode
        except subprocess.TimeoutExpired: timeout, status = True, None
    text = (out / 'qemu.log').read_text(errors='replace')
    passed = not timeout and status == 0 and all(text.count(marker) == 1 for marker in MARKERS)
    passed = passed and 'APPLICATION_MODULES_GUEST PASS' in text and 'APPLICATION_MODULES_GUEST FAIL' not in text
    result = {'result': 'PASS' if passed else 'FAIL', 'inputs': inputs, 'kernel_sha256': sha(args.kernel),
        'arguments': arguments, 'command': command, 'timed_out': timeout, 'qemu_exit': status,
        'log_sha256': sha(out / 'qemu.log'), 'markers': {marker: text.count(marker) for marker in MARKERS}}
    (out / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['result'], out / 'validation.json')
    if not passed: raise SystemExit(1)


if __name__ == '__main__': main()
