import java.nio.*;
import java.lang.invoke.MethodHandles;
import java.util.concurrent.atomic.AtomicReference;
import org.lwjgl.*;
import org.lwjgl.system.*;
import org.lwjgl.system.libffi.*;
import static org.lwjgl.system.MemoryUtil.*;
import static org.lwjgl.system.libffi.LibFFI.*;

public final class LwjglSmoke {
    private static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }
    private static void memory() {
        ByteBuffer source = memAlloc(128);
        ByteBuffer target = memCalloc(128);
        try {
            require(memAddress(source) != 0, "allocation");
            memPutLong(memAddress(source), 0x123456789abcdef0L);
            memCopy(memAddress(source), memAddress(target), 8);
            require(target.getLong(0) == 0x123456789abcdef0L, "copy/direct buffer");
            memSet(memAddress(target), 0x35, 128);
            require(target.get(127) == 0x35, "set");
            target = memRealloc(target, 256);
            require(target.get(127) == 0x35, "reallocate");
        } finally { memFree(source); memFree(target); }
        ByteBuffer text = memUTF8("Scarlet 日本語 🍓");
        try { require(memUTF8(memAddress(text)).equals("Scarlet 日本語 🍓"), "UTF-8"); }
        finally { memFree(text); }
        try (MemoryStack stack = MemoryStack.stackPush()) {
            IntBuffer values = stack.ints(17, 25);
            require(values.get(0) + values.get(1) == 42, "thread stack");
        }
    }
    private static final class DoubleCallback implements CallbackI {
        private final Callback.Descriptor descriptor;
        DoubleCallback(FFICIF cif) {
            descriptor = new Callback.Descriptor(DoubleCallback.class, MethodHandles.lookup(), cif);
        }
        public Callback.Descriptor getDescriptor() { return descriptor; }
        public void callback(long result, long args) {
            memPutLong(result, memGetInt(memGetAddress(args)) * 2L);
        }
    }
    public static void main(String[] args) throws Exception {
        System.out.println("LWJGL_TEST start " + Version.getVersion());
        require(Platform.get() == Platform.SCARLET, "platform");
        require(Platform.getArchitecture() == Platform.Architecture.ARM64, "architecture");
        require(Class.forName("sun.misc.Unsafe").getModule().getName().equals("jdk.unsupported"), "runtime module");
        memory();
        System.out.println("LWJGL_TEST memory PASS");
        SharedLibrary library = APIUtil.apiCreateLibrary("/app/native/liblwjgl_probe.so");
        try {
            long add = library.getFunctionAddress("lwjgl_probe_add");
            require(add != 0 && JNI.invokeI(17, 25, add) == 42, "JNI downcall");
            require(library.getFunctionAddress("missing_symbol") == 0, "missing symbol");
            require(library.getPath() == null, "opaque handle path");
            try (MemoryStack stack = MemoryStack.stackPush()) {
                ByteBuffer unterminated = stack.malloc(3).put(0, (byte)'b').put(1, (byte)'a').put(2, (byte)'d');
                try { library.getFunctionAddress(unterminated); throw new AssertionError("unterminated symbol accepted"); }
                catch (IllegalArgumentException expected) { }
            }
            try (MemoryStack stack = MemoryStack.stackPush()) {
                FFICIF cif = FFICIF.malloc(stack);
                PointerBuffer types = stack.pointers(ffi_type_sint32.address(), ffi_type_sint32.address());
                require(ffi_prep_cif(cif, FFI_DEFAULT_ABI, ffi_type_sint32, types) == FFI_OK, "CIF");
                IntBuffer a = stack.ints(19), b = stack.ints(23);
                ByteBuffer result = stack.calloc(8);
                ffi_call(cif, add, result, stack.pointers(memAddress(a), memAddress(b)));
                require(result.getInt(0) == 42, "libffi downcall");
            }
            System.out.println("LWJGL_TEST downcall PASS");
            AtomicReference<Throwable> error = new AtomicReference<>();
            Thread[] workers = new Thread[4];
            for (int i = 0; i < workers.length; i++) {
                workers[i] = new Thread(() -> {
                    try {
                        for (int n = 0; n < 200; n++) {
                            memory();
                            require(JNI.invokeI(n, 42 - n, add) == 42, "thread downcall");
                        }
                    } catch (Throwable failure) { error.compareAndSet(null, failure); }
                });
                workers[i].start();
            }
            for (Thread worker : workers) worker.join();
            if (error.get() != null) throw new AssertionError(error.get());
            System.out.println("LWJGL_TEST threads PASS");
            try (MemoryStack stack = MemoryStack.stackPush()) {
                FFICIF cif = FFICIF.malloc(stack);
                require(ffi_prep_cif(cif, FFI_DEFAULT_ABI, ffi_type_sint32,
                                    stack.pointers(ffi_type_sint32.address())) == FFI_OK, "callback CIF");
                long callback = new DoubleCallback(cif).address();
                try {
                    require(JNI.invokeI(21, callback) == 42, "callback");
                    long onThread = library.getFunctionAddress("lwjgl_probe_callback_thread");
                    require(onThread != 0 && JNI.invokePI(callback, 21, onThread) == 42, "native thread callback");
                } finally { Callback.free(callback); }
            }
            System.out.println("LWJGL_TEST callback PASS");
        } finally { library.free(); }
        try { APIUtil.apiCreateLibrary("/app/native/missing.so"); throw new AssertionError("missing library accepted"); }
        catch (UnsatisfiedLinkError expected) { require(expected.getMessage().contains("missing.so"), "loader diagnostic"); }
        System.out.println("LWJGL_TEST PASS");
    }
}
