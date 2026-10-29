# scarlet-bundle-lwjgl

Versioned LWJGL core, GLFW and Vulkan bundles for Scarlet AArch64. The producer builds pinned
sources from the [LWJGL fork](https://github.com/petitstrawberry/lwjgl3/tree/scarlet-3.4.3)
and the [GLFW fork](https://github.com/petitstrawberry/glfw/tree/scarlet-3.5.1),
then publishes native runtime archives in CI. Bundle manifests reference those
archives by URL and SHA-256; image composition does not compile LWJGL.

## Use

Add an explicit layer to the consuming project's image configuration:

```toml
[[images.rootfs.layers]]
kind = "bundle"
source = { git = "https://github.com/petitstrawberry/scarlet-bundle-lwjgl", rev = "<pinned-bundle-commit>" }
subdir = "bundles/lwjgl-3.4.3"
```

LWJGL 3.4.3 installs `lwjgl.jar`, `lwjgl-glfw.jar`, `lwjgl-vulkan.jar`,
`jspecify.jar`, `liblwjgl.so` and `libglfw.so` under
`/usr/lib/lwjgl/3.4.3`. Use the matching JAR and native library together:

```sh
java --enable-native-access=ALL-UNNAMED \
  -Dorg.lwjgl.librarypath=/usr/lib/lwjgl/3.4.3 \
  -Dorg.lwjgl.system.allocator=system \
  -cp "/app/app.jar:/usr/lib/lwjgl/3.4.3/*" \
  example.Main
```

Requires Scarlet's `/bin/scarlet-ld` and a native OpenJDK 25 image with external
JNI loading and the `jdk.unsupported` module. Linux native libraries are not
compatible with Scarlet's native ABI. GLFW additionally requires a running SWS
compositor and the native graphics runtime (`user/lib/scarlet-vulkan` in Scarlet),
which supplies `/lib/libsws_client_c.so`, `/lib/libvulkan.so.1`, the SGFX ICD and
its driver manifest. The runtime must include the native SWS surface changes in
[Scarlet](https://github.com/petitstrawberry/Scarlet/tree/5239a9ac72730072d47e6e9d86c13c8d0e68497c),
[Vulkan-Loader](https://github.com/petitstrawberry/Vulkan-Loader/tree/83f0038b735f08e9a8282ef37b74e1eab1fbf896)
and [SGFX](https://github.com/petitstrawberry/sgfx/tree/12df11ee00f4af173f191079b9365548b1c60301).
The producer builds the pinned SWS client as a link input; its runtime DSO belongs
to Scarlet's graphics package and is not duplicated in this archive.

Create GLFW windows with `GLFW_CLIENT_API = GLFW_NO_API`. Obtain the instance
extensions from `glfwGetRequiredInstanceExtensions` and use
`glfwCreateWindowSurface`. The native backend uses the fork's private
`VK_SGFX_scarlet_surface` extension. It supports window resizing, fullscreen,
keyboard and pointer input, and Vulkan swapchain presentation.

## Scope

This recipe builds Java 8 class sets for core, GLFW and Vulkan, plus the Scarlet
native core and GLFW backend.
Memory allocation/access, direct buffers, UTF-8 strings, memory stacks,
JNI/libffi downcalls, library lookup, and callbacks are validated in a Scarlet
HVF guest using interpretation and C2 compilation. The test also calls Java
from a native pthread. See [producer/VALIDATION.md](producer/VALIDATION.md).

Platform bindings for other operating systems and `LibCStdio` native bindings
are not built. The pinned Scarlet SDK does not provide `fscanf`. Optional
LWJGL modules beyond core, GLFW and Vulkan are not included. OpenGL/EGL,
clipboard, custom cursors, joysticks and IME are not implemented by this GLFW
backend; text input currently uses a US keyboard layout. The SGFX ICD supports
an experimental Vulkan subset and is not Vulkan conformant.
Java multi-release/FFM implementations are not packaged by this recipe.

Library loading uses the process loader's eager/global mode. Library paths
cannot be queried from its opaque handles, so `SharedLibrary.getPath()` returns
`null`. Closing a handle leaves its mappings resident until process exit.
The library has no DSO TLS. libffi callbacks use anonymous executable mappings;
the private libffi symbols do not interpose on the JVM's libffi.

## Build and publish

```sh
nix develop
python3 producer/build.py --version 3.4.3 --output producer/.build/lwjgl-3.4.3
python3 producer/release.py \
  --build-receipt producer/.build/lwjgl-3.4.3/build.json \
  --version v0.2.100 --output producer/artifacts/v0.2.100
```

The output directory must be new. `--source /path/to/lwjgl3` supports local
port development, with `--glfw-source` and `--scarlet-source` for the other source
checkouts; such builds cannot be released. Source revisions and
checksums are in `versions/3.4.3/sources.json`. Port changes belong in the
LWJGL and GLFW forks; build recipes, CI, release packaging and bundle pins belong here.
The producer runs independently of a Scarlet kernel checkout.

CI builds on ARM64 Linux, checks the target ELF and archive, and uploads an
artifact. Producer changes on `main` additionally create a new experimental
release and update the bundle manifest after verifying the uploaded archive.
Existing releases are never overwritten. CI compilation does not substitute
for execution in a Scarlet guest.

## License

The producer is BSD-3-Clause licensed. LWJGL, GLFW, libffi, JSpecify, LLVM compiler-rt
and Rust compiler-builtins retain their respective licenses and notices,
included under `/usr/share/licenses/lwjgl/3.4.3`. The source index identifies
upstream and fork revisions; source code stays in the existing repositories.
