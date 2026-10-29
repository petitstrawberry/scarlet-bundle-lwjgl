# Native core validation

On 2026-10-29, the LWJGL 3.4.3 Scarlet port at
`4b9edd50e1892e62b73d3dcfcbcc2c63897719d7` passed on a diskless native Scarlet
AArch64 guest using HVF on Apple Silicon. No TCG run was used.

The test used OpenJDK 25 with external JNI loading and `jdk.unsupported`.
Both `-Xint` and C2 compilation completed allocation/copy/reallocation,
direct-buffer access, UTF-8, thread-local memory stacks, JNI and libffi calls,
four Java worker threads, and libffi callbacks into Java. A callback invoked
from a native pthread also completed. Missing symbols and library-load
failures returned the expected results. Compilation logs showed level 4
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

The ELF audit rejects foreign OSABI, shared-library dependencies, DSO TLS,
unsupported dynamic flags/relocations, unverified imports and exported private
libffi symbols. Host tests cover damaged cache/payload data, foreign ELF,
unsupported loader flags and rejection of development releases.

These checks cover the core recipe only. Optional LWJGL modules, other OS
bindings, `LibCStdio`, Java FFM/multi-release implementations and broader
application compatibility are not established by this validation.
