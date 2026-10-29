# Native core validation

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
  --sws-client /path/to/libsws_client_c.so --driver /path/to/libsgfx_scarlet_virgl.so \
  --qemu /path/to/hvf-virgl/qemu-system-aarch64 \
  --output producer/artifacts/glfw-vulkan/hvf
```

The desktop image must contain SWS, sbusd and their resources. The harness uses
an isolated initramfs and no network/disk, injects one keyboard event over QMP,
and shuts the guest down. It requires HVF and GL-capable VirtIO GPU support.
