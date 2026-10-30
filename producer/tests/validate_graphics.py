#!/usr/bin/env python3
"""Test the real SWS/Vulkan/LWJGL path using an isolated HVF guest."""
import argparse
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import time
from validate import archive, sha

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('kernel', 'init', 'loader', 'java', 'java-home', 'core', 'desktop', 'vulkan', 'icd', 'sws-client', 'scarlet-ui', 'driver', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--qemu', required=True)
    p.add_argument('--binding', choices=('glfw', 'sdl'), default='glfw')
    p.add_argument('--scale', type=float, default=1.0)
    p.add_argument('--timeout', type=int, default=180)
    p.add_argument('--input-delay', type=float, default=0, help='Seconds to retain the rendered window for visual inspection (0..45)')
    a = p.parse_args()
    if not 0 <= a.input_delay <= 45: p.error('--input-delay must be in 0..45')
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, LC_ALL='C')
    smoke = 'SdlGraphicsSmoke' if a.binding == 'sdl' else 'GraphicsSmoke'
    marker = 'SDL_GRAPHICS' if a.binding == 'sdl' else 'GRAPHICS'
    modules = ('lwjgl.jar', 'lwjgl-' + a.binding + '.jar', 'lwjgl-vulkan.jar')
    if a.binding == 'sdl': modules += ('lwjgl-vma.jar',)
    def run(command, name):
        with (out / name).open('w') as log: subprocess.run([str(x) for x in command], check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
    run([Path(env['JAVA_HOME']) / 'bin/javac', '-cp', os.pathsep.join(str(a.core / name) for name in modules),
         '-d', out / 'classes', HERE / (smoke + '.java')], 'javac.log')
    run([env['SCARLET_RUSTC'], '--edition=2024', '--target=aarch64-unknown-scarlet', '-C', 'panic=abort',
         '-C', 'target-feature=+crt-static', '-C', 'relocation-model=static', '-C', 'link-arg=--no-dynamic-linker',
         '-O', HERE / 'graphics_supervisor.rs', '-o', out / 'supervisor'], 'rustc.log')
    data = a.desktop.read_bytes(); offset = 0; entries = {}
    while True:
        header = data[offset:offset + 110]
        if header[:6] != b'070701': raise ValueError('Expected newc desktop image')
        fields = [int(header[6+i*8:14+i*8], 16) for i in range(13)]
        name = data[offset+110:offset+110+fields[11]-1].decode()
        offset = (offset+110+fields[11]+3) & ~3
        if name == 'TRAILER!!!': break
        entries[name] = (fields[1], data[offset:offset+fields[6]])
        offset = (offset+fields[6]+3) & ~3
    inputs = {'desktop': sha(a.desktop), 'kernel': sha(a.kernel)}
    def add(path, name, executable=False):
        for parent in Path(name).parents:
            if str(parent) != '.': entries[parent.as_posix()] = (0o40755, b'')
        entries[name] = (0o100755 if executable else 0o100644, path.read_bytes()); inputs[name] = sha(path)
    add(a.init, 'init', True); add(a.loader, 'bin/scarlet-ld', True); add(a.java, 'bin/java', True)
    add(out / 'supervisor', 'bin/graphics-test', True)
    entries['app/graphics-binding'] = (0o100644, a.binding.encode())
    add(a.vulkan, 'lib/libvulkan.so.1', True); add(a.icd, 'lib/libvulkan_sgfx.so', True)
    add(a.scarlet_ui, 'lib/libscarlet_ui_window.so', True)
    add(a.sws_client, 'lib/libsws_client_c.so', True); add(a.driver, 'lib/sgfx/libsgfx_scarlet_virgl.so', True)
    for path in a.core.iterdir():
        if path.suffix == '.jar': add(path, 'app/' + path.name)
        elif '.so' in path.suffixes: add(path, 'app/native/' + path.name, True)
    for base, dest in [(a.java_home, 'usr/lib/jvm/' + a.java_home.name), (out / 'classes', 'app/classes')]:
        for path in sorted(base.rglob('*')):
            if path.is_file(): add(path, dest + '/' + path.relative_to(base).as_posix())
    for name in ('share/vulkan', 'share/vulkan/icd.d', 'dev', 'tmp', 'root', 'mnt', 'mnt/newroot'):
        entries[name] = (0o40755, b'')
    entries['share/vulkan/icd.d/sgfx.json'] = (0o100644, json.dumps({'file_format_version':'1.0.0','ICD':{'library_path':'/lib/libvulkan_sgfx.so','api_version':'1.1.0'}}).encode())
    entries['lib/sgfx/scarlet-virgl.sgfx-driver'] = (0o100644, b'abi=2\nname=scarlet-virgl\ngpu_backend=virtio-gpu\nlibrary=libsgfx_scarlet_virgl.so\n')
    entries['etc/sws/config.toml'] = (0o100644, f'[output]\nscale = {a.scale}\n'.encode())
    image = out / 'initramfs.cpio'; archive([(n, *v) for n,v in sorted(entries.items())], image)
    qmp = Path('/tmp/lwjgl-graphics-' + str(os.getpid()) + '.sock')
    command = [a.qemu, '-machine', 'virt,gic-version=3', '-accel', 'hvf', '-cpu', 'host', '-m', '4G', '-smp', '4',
               '-global', 'virtio-mmio.force-legacy=false', '-display', 'cocoa,gl=on', '-device', 'virtio-gpu-gl-device', '-device', 'virtio-keyboard-device', '-device', 'virtio-mouse-device',
               '-nic', 'none', '-monitor', 'none', '-serial', 'stdio', '-qmp', 'unix:' + str(qmp) + ',server=on,wait=off', '-no-reboot',
               '-kernel', str(a.kernel), '-initrd', str(image), '-append', 'console=ttyAMA0 init.exec=/bin/graphics-test']
    timed_out = False; sent = False; connection = None
    with (out / 'qemu.log').open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            start = time.monotonic()
            while process.poll() is None and time.monotonic()-start < a.timeout:
                text = (out / 'qemu.log').read_text(errors='replace')
                if marker + ' READY_INPUT' in text and not sent:
                    time.sleep(a.input_delay)
                    connection = socket.socket(socket.AF_UNIX); connection.settimeout(5); connection.connect(str(qmp))
                    stream = connection.makefile('rwb', buffering=0)
                    json.loads(stream.readline())
                    def q(command, arguments=None):
                        stream.write(json.dumps({'execute':command, **({'arguments':arguments} if arguments else {})}).encode()+b'\n')
                        while True:
                            response = json.loads(stream.readline())
                            if 'error' in response: raise RuntimeError(response)
                            if 'return' in response: return response['return']
                    q('qmp_capabilities')
                    try: q('screendump', {'filename':str(out / 'frame.ppm')})
                    except RuntimeError as error: (out / 'capture-error.txt').write_text(str(error))
                    q('send-key', {'keys':[{'type':'qcode','data':'a'}], 'hold-time':80})
                    sent = True
                time.sleep(.1)
            if process.poll() is None: timed_out = True; process.terminate()
            process.wait(timeout=10)
        finally:
            if process.poll() is None: process.kill(); process.wait()
            if connection: connection.close()
            qmp.unlink(missing_ok=True)
    text = (out / 'qemu.log').read_text(errors='replace')
    compiled = all(re.search(r'\d+\s+\d+\s+[! ]*b\s+4\s+' + re.escape(smoke + '::' + method), text) for method in ('render', 'swapchain'))
    passed = compiled and not timed_out and process.returncode == 0 and sent and marker + ' PASS' in text and 'GRAPHICS_GUEST PASS' in text
    if a.binding == 'sdl': passed = passed and 'VMA_NATIVE PASS' in text
    result = {'result':'PASS' if passed else 'FAIL', 'inputs':inputs, 'command':command, 'qemu_exit':process.returncode,
              'binding':a.binding, 'timed_out':timed_out, 'input_sent':sent, 'c2_render_and_swapchain':compiled, 'log_sha256':sha(out / 'qemu.log')}
    (out / 'validation.json').write_text(json.dumps(result,indent=2)+'\n'); print(result['result'], out)
    if not passed: raise SystemExit(1)

if __name__ == '__main__': main()
