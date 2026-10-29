# scarlet-bundle-lwjgl

Versioned LWJGL core bundles for Scarlet AArch64. The producer builds pinned
sources from the [LWJGL fork](https://github.com/petitstrawberry/lwjgl3/tree/scarlet-3.4.3)
and publishes native runtime archives in CI. Bundle manifests reference those
archives by URL and SHA-256; image composition does not compile LWJGL.

## Use

Add an explicit layer to the consuming project's image configuration:

```toml
[[images.rootfs.layers]]
kind = "bundle"
source = { git = "https://github.com/petitstrawberry/scarlet-bundle-lwjgl", rev = "<pinned-bundle-commit>" }
subdir = "bundles/lwjgl-3.4.3"
```

LWJGL 3.4.3 installs `lwjgl.jar`, `jspecify.jar` and `liblwjgl.so` under
`/usr/lib/lwjgl/3.4.3`. Use the matching JAR and native library together:

```sh
java --enable-native-access=ALL-UNNAMED \
  -Dorg.lwjgl.librarypath=/usr/lib/lwjgl/3.4.3 \
  -Dorg.lwjgl.system.allocator=system \
  -cp /app/app.jar:/usr/lib/lwjgl/3.4.3/lwjgl.jar:/usr/lib/lwjgl/3.4.3/jspecify.jar \
  example.Main
```

Requires Scarlet's `/bin/scarlet-ld` and a native OpenJDK 25 image with external
JNI loading and the `jdk.unsupported` module. Linux native libraries are not
compatible with Scarlet's native ABI.

## Scope

This recipe builds the core Java 8 class set and the Scarlet native core.
Memory allocation/access, direct buffers, UTF-8 strings, memory stacks,
JNI/libffi downcalls, library lookup, and callbacks are validated in a Scarlet
HVF guest using interpretation and C2 compilation. The test also calls Java
from a native pthread. See [producer/VALIDATION.md](producer/VALIDATION.md).

Platform bindings for other operating systems and `LibCStdio` native bindings
are not built. The pinned Scarlet SDK does not provide `fscanf`. Optional
LWJGL modules, including GLFW, graphics and audio bindings, are not included.
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
  --version v0.1.100 --output producer/artifacts/v0.1.100
```

The output directory must be new. `--source /path/to/lwjgl3` supports local
port development; such builds cannot be released. Source revisions and
checksums are in `versions/3.4.3/sources.json`. Port changes belong in the
LWJGL fork; build recipes, CI, release packaging and bundle pins belong here.
The producer runs independently of a Scarlet kernel checkout.

CI builds on ARM64 Linux, checks the target ELF and archive, and uploads an
artifact. Producer changes on `main` additionally create a new experimental
release and update the bundle manifest after verifying the uploaded archive.
Existing releases are never overwritten. CI compilation does not substitute
for execution in a Scarlet guest.

## License

The producer is BSD-3-Clause licensed. LWJGL, libffi, JSpecify, LLVM compiler-rt
and Rust compiler-builtins retain their respective licenses and notices,
included under `/usr/share/licenses/lwjgl/3.4.3`. The source index identifies
upstream and fork revisions; source code stays in the existing repositories.
