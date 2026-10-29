"""Build pinned native SDL3 and LWJGL application modules."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from audit import audit

MODULES = ('sdl', 'stb', 'freetype', 'shaderc', 'spvc', 'vma', 'openal', 'opengl')
DEPENDENCIES = ('sdl', 'freetype', 'vulkan_headers', 'shaderc', 'glslang',
                'spirv_tools', 'spirv_headers', 'spirv_cross', 'openal', 'glvnd')


def build_applications(source, scarlet, scarlet_ui, spec, out, lib, core_classes,
                       builtins, env, run, download, extract, jobs):
    logs = out / 'logs'
    runtime = Path(env['SCARLET_NATIVE_RUNTIME'])
    cc, cxx = env['SCARLET_NATIVE_CC'], env['SCARLET_NATIVE_CXX']
    resource = subprocess.check_output([cc, '-print-resource-dir'], text=True, env=env).strip()
    sources = {name: extract(download(spec[name], spec[name]['commit'] + '.tar.gz'),
                            out / (name + '-source')) for name in DEPENDENCIES}
    # Prevent upstream version probes from finding the producer's parent Git repo.
    native_env = dict(env, GIT_CEILING_DIRECTORIES=str(out), SOURCE_DATE_EPOCH='1787443200')
    for name, directory in [('glslang', 'glslang'), ('spirv_tools', 'spirv-tools'),
                            ('spirv_headers', 'spirv-headers')]:
        destination = sources['shaderc'] / 'third_party' / directory
        if destination.exists(): raise ValueError('Unexpected populated shader dependency: ' + directory)
        shutil.move(sources[name], destination)
        sources[name] = destination
    flags = ['--target=aarch64-unknown-none-elf', '-O2', '-fPIC', '-fno-stack-protector',
             '-mno-outline-atomics', '-nostdinc', '-isystem', resource + '/include',
             '-isystem', str(runtime / 'include'), '-D__scarlet__=1']
    cxx_flags = ['-nostdinc++', '-isystem', str(runtime / 'include/c++/v1'),
                 *flags, '-fno-exceptions', '-fno-rtti']
    toolchain = out / 'applications-toolchain.cmake'
    settings = {
        'CMAKE_SYSTEM_NAME': 'Scarlet', 'CMAKE_SYSTEM_PROCESSOR': 'aarch64',
        'CMAKE_C_COMPILER': cc, 'CMAKE_CXX_COMPILER': cxx, 'CMAKE_ASM_COMPILER': cc,
        'CMAKE_C_COMPILER_TARGET': 'aarch64-unknown-none-elf',
        'CMAKE_CXX_COMPILER_TARGET': 'aarch64-unknown-none-elf',
        'CMAKE_ASM_COMPILER_TARGET': 'aarch64-unknown-none-elf',
        'CMAKE_AR': env['SCARLET_NATIVE_AR'], 'CMAKE_RANLIB': env['SCARLET_NATIVE_RANLIB'],
        'CMAKE_TRY_COMPILE_TARGET_TYPE': 'STATIC_LIBRARY',
        'CMAKE_MODULE_PATH': str(runtime / 'share/scarlet/cmake'),
        'CMAKE_C_FLAGS_INIT': ' '.join(flags), 'CMAKE_CXX_FLAGS_INIT': ' '.join(cxx_flags),
        'CMAKE_ASM_FLAGS_INIT': ' '.join(flags), 'CMAKE_POSITION_INDEPENDENT_CODE': 'ON',
    }
    toolchain.write_text(''.join('set(' + key + ' ' + json.dumps(value) + ')\n'
                                 for key, value in settings.items()))

    def cmake(name, options, target=None):
        build = out / (name + '-build')
        command = ['cmake', '-G', 'Ninja', '-S', sources[name], '-B', build,
                   '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain)]
        command += ['-D' + key + '=' + str(value) for key, value in options.items()]
        run(command, out, logs / (name + '-configure.log'), native_env)
        command = ['cmake', '--build', build, '--parallel', str(jobs)]
        if target: command += ['--target', target]
        run(command, out, logs / (name + '-build.log'), native_env)
        return build

    def link(name, objects, archives, symbols, needed=()):
        exports = out / (name + '.exports')
        exports.write_text('{ global: ' + symbols + ' local: *; };\n')
        target = lib / name
        command = [cxx, '--target=aarch64-unknown-none-elf', '-nostdlib', '-fuse-ld=lld',
                   '-Wl,-shared', '-Wl,-Bdynamic', '-Wl,--hash-style=both',
                   '-Wl,-z,max-page-size=4096', '-Wl,-z,start-stop-visibility=hidden',
                   '-Wl,-soname,' + name, '-Wl,--version-script=' + str(exports), *objects,
                   '-Wl,--start-group', '-Wl,--whole-archive', *archives,
                   '-Wl,--no-whole-archive', runtime / 'lib/libc++.a',
                   runtime / 'lib/libc++abi.a', runtime / 'lib/libscarlet_cxx_support.a',
                   builtins, '-Wl,--end-group', *needed, '-Wl,--gc-sections', '-o', target]
        run(command, out, logs / (name + '-link.log'), native_env)
        with target.open('r+b') as stream:
            if stream.read(4) != b'\x7fELF': raise ValueError('Expected target ELF')
            stream.seek(7); stream.write(b'\x53')
        return target

    core = source / 'modules/lwjgl/core/src'
    def bindings(module, cpp=False):
        root = source / 'modules/lwjgl' / module / 'src'
        includes = [core / 'main/c', core / 'main/c/scarlet', root / 'main/c', Path(__file__).resolve().parent / 'cache']
        if cpp: includes += [sources['vulkan_headers'] / 'include']
        options = [*(cxx_flags if cpp else flags), '-fvisibility=hidden',
                   '-DLWJGL_SCARLET', '-DLWJGL_arm64', '-DNDEBUG',
                   '-std=c++17' if cpp else '-std=c11']
        for directory in includes: options += ['-I', str(directory)]
        paths = sorted((root / 'generated/c').glob('*.cpp' if cpp else '*.c'))
        if module == 'opengl': paths = [path for path in paths if not path.name.startswith('org_lwjgl_opengl_WGL')]
        directory = out / (module + '-objects'); directory.mkdir()
        def compile(path):
            obj = directory / (path.stem + '.o')
            run([cxx if cpp else cc, *options, '-c', path, '-o', obj], out,
                logs / (module + '-' + path.stem + '.log'), native_env)
            return obj
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            objects = list(pool.map(compile, paths))
        if not objects: raise ValueError('No native binding sources: ' + module)
        package = 'util_vma' if module == 'vma' else module
        return link('liblwjgl_' + module + '.so', objects, [], 'Java_org_lwjgl_' + package + '_*;')

    bindings('stb')
    bindings('opengl')
    bindings('vma', cpp=True)
    ft_options = {'FT_DISABLE_' + name: 'ON' for name in ('ZLIB', 'BZIP2', 'PNG', 'HARFBUZZ', 'BROTLI')}
    ft = cmake('freetype', ft_options)
    link('libfreetype.so', [], [ft / 'libfreetype.a'], 'FT*;')

    shader_options = {key: 'ON' for key in ('SHADERC_SKIP_TESTS', 'SHADERC_SKIP_EXAMPLES',
        'SHADERC_SKIP_EXECUTABLES', 'SHADERC_SKIP_COPYRIGHT_CHECK', 'SPIRV_SKIP_TESTS',
        'SPIRV_SKIP_EXECUTABLES', 'SPIRV_TOOLS_BUILD_STATIC', 'ENABLE_OPT', 'SHADERC_ENABLE_HLSL')}
    shader_options.update({key: 'OFF' for key in ('SHADERC_ENABLE_WERROR_COMPILE',
        'ENABLE_GLSLANG_BINARIES', 'GLSLANG_TESTS', 'ENABLE_EXCEPTIONS', 'ENABLE_RTTI',
        'SPIRV_HEADERS_ENABLE_TESTS', 'SPIRV_HEADERS_ENABLE_INSTALL')})
    shader = cmake('shaderc', shader_options, 'shaderc_combined')
    # The static API object has hidden visibility. Compile upstream's shared API
    # object, with its own SHADERC_IMPLEMENTATION/SHAREDLIB definitions.
    api_objects = re.findall(r'^build ([^ :]*shaderc_shared\.dir/src/shaderc\.cc\.(?:obj|o)):',
                             (shader / 'build.ninja').read_text(), re.M)
    if len(api_objects) != 1: raise ValueError('Expected one shared shaderc API object')
    run(['cmake', '--build', shader, '--target', api_objects[0]], out,
        logs / 'shaderc-shared-api.log', native_env)
    archives = [shader / path for path in ('libshaderc_util/libshaderc_util.a',
        'third_party/glslang/glslang/libglslang.a', 'third_party/glslang/SPIRV/libSPIRV.a',
        'third_party/spirv-tools/source/libSPIRV-Tools.a',
        'third_party/spirv-tools/source/opt/libSPIRV-Tools-opt.a')]
    link('libshaderc.so', [shader / api_objects[0]], archives, 'shaderc_*;')
    cross = cmake('spirv_cross', {'SPIRV_CROSS_EXCEPTIONS_TO_ASSERTIONS': 'ON',
        'SPIRV_CROSS_CLI': 'OFF', 'SPIRV_CROSS_ENABLE_TESTS': 'OFF',
        'SPIRV_CROSS_STATIC': 'ON', 'SPIRV_CROSS_SHARED': 'OFF', 'SPIRV_CROSS_FORCE_PIC': 'ON'})
    link('libspirv-cross.so', [], sorted(cross.glob('libspirv-cross-*.a')), 'spvc_*;')

    # Real ScarletUI and SWS libraries are link inputs. The platform supplies
    # them at /lib; the LWJGL package does not duplicate those runtimes.
    ui_target = out / 'scarlet-ui-link-target'
    run(['cargo', 'build', '--locked', '--manifest-path', scarlet_ui / 'Cargo.toml',
         '-p', 'scarlet-ui-window-c', '--release', '--target', 'aarch64-unknown-scarlet'],
        out, logs / 'scarlet-ui-link.log', dict(env, CARGO_TARGET_DIR=str(ui_target)))
    sws = out / 'sws-target/aarch64-unknown-scarlet/release/libsws_client_c.so'
    ui = ui_target / 'aarch64-unknown-scarlet/release/libscarlet_ui_window.so'
    sdl_options = {key: 'OFF' for key in ('SDL_SHARED', 'SDL_TESTS', 'SDL_EXAMPLES',
        'SDL_RENDER', 'SDL_GPU', 'SDL_AUDIO', 'SDL_JOYSTICK', 'SDL_HAPTIC', 'SDL_SENSOR',
        'SDL_CAMERA', 'SDL_DIALOG', 'SDL_OPENGL', 'SDL_OPENGLES', 'SDL_ARMNEON',
        'SDL_PTHREADS_SEM', 'LIBC_HAS_LROUND', 'LIBC_HAS_LROUNDF')}
    sdl_options.update({key: 'ON' for key in ('SDL_STATIC', 'SDL_PTHREADS', 'SDL_VULKAN', 'SDL_LIBC')})
    sdl_options.update(SCARLET_SWS_INCLUDE_DIR=str(scarlet / 'user/lib/sws-client-c/include'),
        SCARLET_UI_INCLUDE_DIR=str(scarlet_ui / 'crates/scarlet-ui-window-c/include'),
        SCARLET_SWS_LIBRARY=str(sws), SCARLET_UI_LIBRARY=str(ui))
    sdl = cmake('sdl', sdl_options)
    link('libSDL3.so', [], [sdl / 'libSDL3.a'], 'SDL_*;',
         ['-L' + str(sws.parent), '-L' + str(ui.parent), '-l:libsws_client_c.so', '-l:libscarlet_ui_window.so'])

    # OpenAL's C implementation avoids an unavailable C++ unwind runtime.
    # Code generation runs on the host; only the resulting tables enter target C.
    al_build = out / 'openal-build'
    run(['cmake', '-G', 'Ninja', '-S', sources['openal'] / 'native-tools',
         '-B', al_build / 'native-tools', '-DCMAKE_POLICY_VERSION_MINIMUM=3.5'],
        out, logs / 'openal-native-tools.log', env)
    al_options = {'CMAKE_POLICY_VERSION_MINIMUM': '3.5', 'LIBTYPE': 'STATIC',
        'ALSOFT_UTILS': 'OFF', 'ALSOFT_EXAMPLES': 'OFF', 'ALSOFT_TESTS': 'OFF',
        'ALSOFT_NO_CONFIG_UTIL': 'ON', 'ALSOFT_EMBED_HRTF_DATA': 'OFF',
        'CMAKE_DISABLE_FIND_PACKAGE_PkgConfig': 'ON'}
    for name in ('ALSA', 'OSS', 'SOLARIS', 'SNDIO', 'QSA', 'WINMM', 'DSOUND', 'WASAPI',
                 'PORTAUDIO', 'PULSEAUDIO', 'JACK', 'COREAUDIO', 'OPENSL', 'SDL2', 'WAVE'):
        al_options['ALSOFT_BACKEND_' + name] = 'OFF'
    al = cmake('openal', al_options, 'OpenAL')
    link('libopenal.so', [], [al / 'libopenal.a'], 'al[A-Z]*; alc[A-Z]*;')

    gl_build = out / 'glvnd-build'
    cross_file = out / 'glvnd-cross.ini'
    gl_flags = [*flags]
    # Meson drops an ordinary builtin -isystem path despite -nostdinc.
    position = gl_flags.index('-isystem')
    gl_flags[position:position + 2] = ['-Xclang', '-internal-isystem', '-Xclang', resource + '/include']
    link_flags = ['--target=aarch64-unknown-none-elf', '-nostdlib', '-fuse-ld=lld',
        '-Wl,-shared', '-Wl,-Bdynamic', '-Wl,--hash-style=both', '-Wl,-z,max-page-size=4096',
        str(runtime / 'lib/libscarlet_cxx_support.a'), str(builtins)]
    cross_file.write_text('[binaries]\nc=' + repr(cc) + '\nar=' + repr(env['SCARLET_NATIVE_AR']) +
        '\n[host_machine]\nsystem=\'scarlet\'\ncpu_family=\'aarch64\'\ncpu=\'aarch64\'\nendian=\'little\'\n' +
        '[built-in options]\nc_args=' + repr(gl_flags) + '\nc_link_args=' + repr(link_flags) +
        '\n[properties]\nneeds_exe_wrapper=true\n')
    run(['meson', 'setup', gl_build, sources['glvnd'], '--cross-file', cross_file,
         '--buildtype=release', '-Dx11=disabled', '-Dglx=disabled', '-Degl=false',
         '-Dgles1=false', '-Dgles2=false', '-Dhgl=false', '-Dtls=false', '-Ddispatch-tls=false',
         '-Dasm=disabled', '-Dentrypoint-patching=disabled', '-Db_lundef=false'],
        out, logs / 'glvnd-configure.log', native_env)
    run(['meson', 'compile', '-C', gl_build, '-j', str(jobs), 'OpenGL', 'GLdispatch'],
        out, logs / 'glvnd-build.log', native_env)
    installed = out / 'glvnd-install'
    run(['meson', 'install', '-C', gl_build, '--destdir', installed, '--no-rebuild'],
        out, logs / 'glvnd-install.log', native_env)
    for name in ('OpenGL', 'GLdispatch'):
        matches = list(installed.rglob('lib' + name + '.so.0.0.0'))
        if len(matches) != 1: raise ValueError('Expected installed GL library: ' + name)
        target = lib / ('lib' + name + '.so.0')
        shutil.copyfile(matches[0], target)
        with target.open('r+b') as stream:
            stream.seek(7); stream.write(b'\x53')

    jdk = Path(env['JAVA_HOME'])
    for module in MODULES:
        root = source / 'modules/lwjgl' / module / 'src'
        paths = sorted((root / 'main/java').rglob('*.java')) + sorted((root / 'generated/java').rglob('*.java'))
        classes = out / (module + '-classes'); classes.mkdir()
        arguments = out / (module + '-javac.args')
        arguments.write_text('\n'.join(json.dumps(str(path)) for path in paths))
        classpath = os.pathsep.join(map(str, [core_classes, out / 'vulkan-classes', lib / 'jspecify.jar']))
        run([jdk / 'bin/javac', '-source', '8', '-target', '8', '-encoding', 'UTF-8',
             '-cp', classpath, '-d', classes, '@' + str(arguments)], out, logs / (module + '-javac.log'), env)
        run([jdk / 'bin/jar', '--create', '--date=2026-08-23T00:00:00Z', '--file',
             lib / ('lwjgl-' + module + '.jar'), '-C', classes, '.'], out, logs / (module + '-jar.log'), env)

    legal = out / 'image/usr/share/licenses/lwjgl' / lib.name
    licenses = {'sdl': ['LICENSE.txt'], 'freetype': ['LICENSE.TXT', 'docs/FTL.TXT', 'docs/GPLv2.TXT'],
        'vulkan_headers': ['LICENSE.md'],
        'shaderc': ['LICENSE'], 'glslang': ['LICENSE.txt'], 'spirv_tools': ['LICENSE'],
        'spirv_headers': ['LICENSE'], 'spirv_cross': ['LICENSE'], 'openal': ['COPYING'],
        'glvnd': ['README.md']}
    for name, paths in licenses.items():
        destination = legal / name; destination.mkdir()
        for path in paths:
            shutil.copyfile(sources[name] / path, destination / Path(path).name)
        if (sources[name] / 'LICENSES').is_dir():
            shutil.copytree(sources[name] / 'LICENSES', destination / 'LICENSES')
    shutil.copytree(runtime / 'share/licenses/LLVM', legal / 'LLVM-runtime')
    shutil.copyfile(runtime / 'share/licenses/ScarletSDK.txt', legal / 'ScarletSDK.txt')
    shutil.copyfile(source / 'modules/lwjgl/vma/vma_license.txt', legal / 'VMA.txt')
    # Each bundled stb source carries its own author and dual-license notices.
    stb_notices = legal / 'stb'; stb_notices.mkdir()
    for path in (source / 'modules/lwjgl/stb/src/main/c').iterdir():
        if path.suffix in ('.h', '.c'): shutil.copyfile(path, stb_notices / path.name)
    profiles = {'liblwjgl_stb.so': 'stb', 'liblwjgl_opengl.so': 'opengl', 'liblwjgl_vma.so': 'vma',
        'libfreetype.so': 'freetype', 'libshaderc.so': 'shaderc', 'libspirv-cross.so': 'spvc',
        'libSDL3.so': 'sdl', 'libopenal.so': 'openal', 'libOpenGL.so.0': 'gl', 'libGLdispatch.so.0': 'gldispatch'}
    return {'elf': {name: audit(lib / name, profile) for name, profile in profiles.items()},
            'profiles': profiles, 'modules': list(MODULES),
            'openal_profile': '1.19.1 C; loopback/null; no native playback backend',
            'spvc_profile': 'exceptions-to-assertions; malformed input may abort'}
