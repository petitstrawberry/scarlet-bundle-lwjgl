# Native core validation

## Application module producer

The producer also builds SDL3, STB, FreeType, shaderc, SPIRV-Cross, VMA,
OpenAL and OpenGL bindings from the immutable source revisions in
`versions/3.4.3/sources.json`. Native changes live in the corresponding forks.
The bundle contains build recipes and artifact references. SWS and ScarletUI
remain platform runtime dependencies; their link inputs are built from the
pinned sources and are not copied into the LWJGL payload.

`native-contracts.json` fixes the verified import/dependency and public export
contracts for each library. New imports require native validation before the
contract changes. The release verifier repeats these audits after extracting
the archive. The checks reject DSO TLS, build RPATH, unsupported relocation
types, hidden shader API mistakes and exported private runtime symbols.

The headless application suite exercises SDL loading, PNG decode and thread
flags, font rasterization, GLSL-to-SPIR-V compilation, reflection and compiler
diagnostics across four threads, PCM loopback mixing/error reporting, OpenGL
dispatch loading/context rejection, and VMA library initialization:

```sh
nix develop --command python3 producer/tests/validate_applications.py \
  --kernel /path/to/Image --init /path/to/init --loader /path/to/scarlet-ld \
  --java /path/to/java --java-home /path/to/openjdk-25 \
  --core /path/to/runtime/usr/lib/lwjgl/3.4.3 --font /path/to/font.ttf \
  --sws-client /path/to/libsws_client_c.so \
  --scarlet-ui /path/to/libscarlet_ui_window.so \
  --qemu /path/to/qemu-system-aarch64 \
  --output producer/artifacts/application-modules/hvf
```

The VM uses HVF, ephemeral test state and no network or disk. The result records
all runtime input hashes and checks every success marker and process exit.
It does not test SDL presentation or GPU memory allocation; those require a
graphics guest. OpenAL currently uses the C implementation in 1.19.1 with
loopback/null support and no native hardware playback/capture backend. OpenGL
provides dispatch without a rendering vendor. SPIRV-Cross uses its upstream
exceptions-to-assertions profile; malformed input may abort.

The earlier validation records below concern the specific artifacts and
source revisions named in each section.

On 2026-10-29, the LWJGL 3.4.3 Scarlet port at
`0c092dbfc3221c5a25e3657e1b0954779f2e5ff2` passed on a diskless native Scarlet
AArch64 guest using HVF on Apple Silicon. No TCG run was used.

The test used OpenJDK 25 with external JNI loading and `jdk.unsupported`.
Both `-Xint` and C2 compilation completed allocation/copy/reallocation,
direct-buffer access, UTF-8, thread-local memory stacks, JNI and libffi calls,
four Java worker threads, and libffi callbacks into Java. A callback invoked
from a native pthread also completed. Missing symbols and library-load
failures returned the expected results. Unterminated symbol names were rejected
before entering the native loader. Compilation logs showed level 4
compilation of `LwjglSmoke::memory` and `LwjglSmoke$DoubleCallback::callback`.

Run the test against a selected runtime and kernel:

```sh
nix develop --command python3 producer/tests/validate.py \
  --kernel /path/to/Scarlet-Image --init /path/to/native-init \
  --loader /path/to/scarlet-ld --java /path/to/native-java \
  --java-home /path/to/openjdk-25 \
  --core producer/.build/lwjgl-3.4.3/image/usr/lib/lwjgl/3.4.3 \
  --output producer/.build/hvf-validation \
  --qemu /path/to/hvf-compatible/qemu-system-aarch64
```

The output records the kernel and payload checksums, QEMU command, compilation
and guest logs, and pass/fail evidence. Use a new output directory for each
run. The VM uses an isolated initramfs and shuts down after its tests.

The core ELF audit rejects foreign OSABI, shared-library dependencies, DSO TLS,
unsupported dynamic flags/relocations, unverified imports and exported private
libffi symbols. Host tests cover damaged cache/payload data, foreign ELF,
unsupported loader flags and rejection of development releases.

The preceding checks cover the core recipe only. Optional LWJGL modules, other OS
bindings, `LibCStdio`, Java FFM/multi-release implementations and broader
application compatibility are not established by this validation.

## CI artifact execution

The published [LWJGL v0.1.2 archive](https://github.com/petitstrawberry/scarlet-bundle-lwjgl/releases/tag/v0.1.2)
was downloaded and its inventory and bundle manifest verified. The same guest
suite passed using this exact archive and the Java 25 artifact from
[OpenJDK CI run 40820293553](https://github.com/petitstrawberry/scarlet-bundle-openjdk/actions/runs/40820293553).
The [LWJGL build and publication workflow](https://github.com/petitstrawberry/scarlet-bundle-lwjgl/actions/runs/40820826836)
and both OpenJDK CI recipes completed successfully.

| Input | SHA-256 |
| --- | --- |
| Native LWJGL | `1d542db88988e92a3aad0c0a6847bbccc5051e2bd33651fa3282172d0e92bb9d` |
| LWJGL JAR | `270a1726a523d3468a4657f3039a23702f5bc6733ee03c457998a6bb79dfc928` |
| Native Java | `403a9bd1706d80f12418297d1250970439e53ece9d215f23d76b72a51e11cd57` |
| Java modules | `4b97bc375eec00f14e6f1b7596084e7aee6ca04a3d98f16fb2eab73869ab77aa` |
| Scarlet kernel | `f474d06aeb849efbb7d0e13009c6d61537dd9b0656f2b1a2b8485fe9726c0d16` |
| Guest log | `be610166b2358df290e86764dcedac611407dc9dc59e29e50746c56401264ff1` |

OpenJDK producer revision: `200b6a6a4ee7938d641b25be5a96f14122e0b26c`.
The runtime-module change is proposed in [OpenJDK bundle PR #6](https://github.com/petitstrawberry/scarlet-bundle-openjdk/pull/6),
stacked on its native JNI loader prerequisite, PR #5. These PRs were not merged
as part of this validation.

## Native GLFW and Vulkan WSI

On 2026-10-29 the native graphics test passed with OpenJDK 25 C2 in an
AArch64 HVF guest. It used real SWS windows and the SGFX VirGL backend:

- GLFW initialization selected `GLFW_PLATFORM_SCARLET`; the required Vulkan
  extensions were `VK_KHR_surface` and `VK_SGFX_scarlet_surface`.
- Instance/device/surface creation and single-device Vulkan 1.1 presentation
  queries succeeded, including the present rectangle and `AcquireNextImage2`.
- Clear/submit/present completed at 320×240 and again at 384×256 after resize.
  The old swapchain returned `VK_ERROR_OUT_OF_DATE_KHR` before replacement.
- A key injected through QEMU's keyboard device reached both the GLFW key and
  character callbacks. The framebuffer resize callback also ran.
- Surface and swapchain teardown completed without destroying the GLFW window.
  C2 level 4 compilation of `GraphicsSmoke::render` and `::swapchain` was checked.

The earlier interpreter run also completed window/presentation, resize and
keyboard handling. The expanded test above is validated with C2. These checks
establish API and guest execution, not Vulkan conformance. QMP screendump does
not expose the GL scanout surface on this QEMU build, so pixel output was not
verified by screenshot. OpenGL, audio, IME, multi-monitor and wider application
compatibility are outside this test.

The graphics test accepts explicit runtime inputs and records their SHA-256
values, the HVF command, guest log checksum and pass/fail result:

```sh
nix develop --command python3 producer/tests/validate_graphics.py \
  --kernel /path/to/Image --init /path/to/init --loader /path/to/scarlet-ld \
  --java /path/to/java --java-home /path/to/openjdk-25 \
  --core /path/to/runtime/usr/lib/lwjgl/3.4.3 \
  --desktop /path/to/desktop.cpio \
  --vulkan /path/to/libvulkan.so.1 --icd /path/to/libvulkan_sgfx.so \
  --scarlet-ui /path/to/libscarlet_ui_window.so \
  --sws-client /path/to/libsws_client_c.so --driver /path/to/libsgfx_scarlet_virgl.so \
  --qemu /path/to/hvf-virgl/qemu-system-aarch64 \
  --output producer/artifacts/glfw-vulkan/hvf
```

The desktop image must contain SWS, sbusd and their resources. The harness uses
an isolated initramfs and no network/disk, injects one keyboard event over QMP,
and shuts the guest down. It requires HVF and GL-capable VirtIO GPU support.

### Published graphics archive

The exact [v0.2.4 CI archive](https://github.com/petitstrawberry/scarlet-bundle-lwjgl/releases/tag/v0.2.4)
passed the expanded C2 graphics test. [CI run 40827289362](https://github.com/petitstrawberry/scarlet-bundle-lwjgl/actions/runs/40827289362)
completed its build, ELF/module checks and archive verification. The published
archive was downloaded again and matched the CI checksum.

| Input | SHA-256 |
| --- | --- |
| Release archive | `0f89ce23fb53c7c749b3741b7569ce126c83fd3fc8c77b73e35374dd1424331b` |
| GLFW native library | `14f65e81ee06125de7143c678cca50a136fe03d899caf2dd72d6e6293b068e69` |
| LWJGL native core | `1d542db88988e92a3aad0c0a6847bbccc5051e2bd33651fa3282172d0e92bb9d` |
| GLFW JAR | `bde6089364bf5d3fc1c2891feffeb4248a23c5c4d3bbb57e35e86179a01aab6f` |
| Vulkan JAR | `5181d989e943526cb9bf9f3360d6b11caacd3857b217aad74d43f51d8830d0d7` |
| SWS client | `f9f98d301b4c62a4bff52b958bfa2791b41428024a7b801f380099f85664a0a8` |
| Vulkan loader | `01332ad8da92bf6f183d788f5d4266658f26324e2416d97fac42245365d579ec` |
| SGFX ICD | `9f6247464d8b257c763436f2368f37d9bd7121a9f9dc4ae626eb4927a3fa751b` |
| VirGL backend | `f9160d6b636658d2e4efac11e6b9ff5e3ef0da95d89bc92c975351943d014de6` |
| Guest log | `24c30e08aab562c75ddf65ff43b3412397bab25cabd972b82388deeb7692d454` |

Runtime source revisions: Vulkan-Loader `83f0038b735f08e9a8282ef37b74e1eab1fbf896`,
SGFX `12df11ee00f4af173f191079b9365548b1c60301`, and the SWS client from Scarlet
`65f8becaa6f08c33183a085a03efa8608e0dac93`. The native runtime integration is
[Scarlet PR #614](https://github.com/petitstrawberry/Scarlet/pull/614).
The release attachment `graphics-validation.json` records all guest input
hashes and the result. The producer archive contains no kernel or SWS runtime.

[SGFX CI run 40827882875](https://github.com/petitstrawberry/sgfx/actions/runs/40827882875)
passed on the pinned ICD revision: native AArch64 and RISC-V builds/lints,
Linux AArch64 WSI checking, and portable tests/lints/documentation with both
upstream and Scarlet toolchains. Native guest execution above covers AArch64;
the RISC-V result is a build check.


## Standard window chrome

The native graphics harness now checks content/frame separation, decoration
and resizable toggles, title updates during presentation, fullscreen/restore,
and output scaling. Pass `--scarlet-ui` with the frame runtime DSO and run
`--scale 1` and `--scale 2`. Both scales passed under HVF with OpenJDK 25 C2
using ScarletUI revision `409b91758b67a0084f411b133c885a88e54b1461`.
A logical 320×240 content area produces a 320×240 or 640×480 swapchain;
384×256 after resize produces 384×256 or 768×512. The old swapchain reports
out-of-date, and frame-only repaints preserve the GPU buffer release contract.
The GL QEMU display does not support this harness's screendump request, so
these results establish functional behavior, not screenshot-based appearance.

## Native application modules

`producer/tests/validate_applications.py` accepts explicit `--kernel`, `--init`,
`--loader`, `--java`, `--java-home`, `--core`, `--font`, `--sws-client`,
`--scarlet-ui`, `--qemu` and `--output` inputs. It runs SDL initialization,
thread-local STB image decoding, FreeType rasterization, concurrent shaderc
compilation and SPIRV-Cross reflection, OpenAL loopback rendering, OpenGL
provider loading and VMA provider loading in an isolated AArch64 HVF guest.
The font must be a TrueType font containing a visible Latin `A` glyph.

Use `validate_graphics.py --binding sdl` with the same explicit graphics inputs
as the GLFW test to exercise SDL windows, decoration changes, Vulkan surface
and swapchain creation, present, resize and injected keyboard/text input.
It also allocates, maps, writes, flushes, invalidates and frees a real Vulkan
buffer through VMA. Both graphics variants require level 4 compilation of the
render and swapchain methods; methods may subsequently deoptimize.

The OpenAL build supports loopback rendering; hardware playback and capture
are not implemented. OpenGL dispatch loading is verified, but no vendor
renderer or OpenGL window context is supplied. The Vulkan frontend remains a
bounded, non-conformant implementation; these checks do not establish general
application compatibility.

On 2026-10-30 the pinned native application sources passed the headless suite
and the SDL Vulkan/VMA graphics suite with OpenJDK 25 under HVF. The additional
four-thread loader test validates 128 overlapping missing-library errors.
These tests require the serialized loader from Scarlet revision
`6e8f3d0fbf532588b5e9f9606317b3f981f23dab` (or its successor); the older loader
can reject concurrent first JNI lookups. The loader was built using the
matching namespaced native Rust TLS runtime.

| Validation input | SHA-256 |
| --- | --- |
| Native loader | `3416b48170fcfb0399858a5b5577050fb295d8151b95e36c60ba26e2f86945e7` |
| Headless guest log | `58072c114c4533dac91d6107a6b10125eb4a6ba3b1d283c0edf5dc9a34a0b9db` |
| SDL/VMA graphics guest log | `48c1d95936e1c8bc4ff11e05d36b8c90feef63480c3f055a9da025d5332142ea` |
