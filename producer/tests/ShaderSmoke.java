import java.nio.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import org.lwjgl.PointerBuffer;
import org.lwjgl.system.MemoryStack;
import org.lwjgl.util.spvc.SpvcReflectedResource;
import static org.lwjgl.util.shaderc.Shaderc.*;
import static org.lwjgl.util.spvc.Spvc.*;

public class ShaderSmoke {
    static final String SOURCE = "#version 450\nlayout(location=0) in vec3 position;\n" +
        "layout(set=0,binding=0) uniform Camera { mat4 transform; } camera;\n" +
        "void main() { gl_Position=camera.transform*vec4(position,1.25); }\n";
    static void check(int result, String operation) {
        if (result != 0) throw new AssertionError(operation + "=" + result);
    }
    static void reflect(ByteBuffer binary) {
        try (MemoryStack stack = MemoryStack.stackPush()) {
            PointerBuffer pointer = stack.mallocPointer(1);
            check(spvc_context_create(pointer), "context");
            long context = pointer.get(0);
            try {
                IntBuffer words = binary.order(ByteOrder.LITTLE_ENDIAN).asIntBuffer();
                check(spvc_context_parse_spirv(context, words, words.remaining(), pointer), "parse SPIR-V");
                check(spvc_context_create_compiler(context, SPVC_BACKEND_NONE, pointer.get(0), SPVC_CAPTURE_MODE_TAKE_OWNERSHIP, pointer), "reflection compiler");
                long compiler = pointer.get(0);
                check(spvc_compiler_create_shader_resources(compiler, pointer), "resources");
                long resources = pointer.get(0);
                PointerBuffer count = stack.mallocPointer(1);
                check(spvc_resources_get_resource_list_for_type(resources, SPVC_RESOURCE_TYPE_UNIFORM_BUFFER, pointer, count), "uniform resources");
                if (count.get(0) != 1) throw new AssertionError("uniform buffer count");
                SpvcReflectedResource resource = SpvcReflectedResource.create(pointer.get(0));
                if (spvc_compiler_get_decoration(compiler, resource.id(), 33) != 0 ||
                    spvc_compiler_get_decoration(compiler, resource.id(), 34) != 0)
                    throw new AssertionError("descriptor binding/set");
                check(spvc_resources_get_resource_list_for_type(resources, SPVC_RESOURCE_TYPE_STAGE_INPUT, pointer, count), "input resources");
                if (count.get(0) != 1) throw new AssertionError("vertex input count");
            } finally { spvc_context_destroy(context); }
        }
    }
    static void compile(int worker) {
        long compiler = shaderc_compiler_initialize();
        long options = shaderc_compile_options_initialize();
        if (compiler == 0 || options == 0) throw new AssertionError("compiler initialization");
        try {
            shaderc_compile_options_set_target_env(options, shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_1);
            for (int n = 0; n < 4; ++n) {
                long result = shaderc_compile_into_spv(compiler, SOURCE, shaderc_glsl_vertex_shader, "worker" + worker + ".vert", "main", options);
                if (result == 0) throw new AssertionError("null compilation result");
                try {
                    if (shaderc_result_get_compilation_status(result) != shaderc_compilation_status_success)
                        throw new AssertionError(shaderc_result_get_error_message(result));
                    ByteBuffer binary = shaderc_result_get_bytes(result).order(ByteOrder.LITTLE_ENDIAN);
                    if (binary.remaining() < 20 || binary.getInt(0) != 0x07230203) throw new AssertionError("invalid SPIR-V");
                    reflect(binary);
                } finally { shaderc_result_release(result); }
            }
            long invalid = shaderc_compile_into_spv(compiler, "#version 450\nvoid main(){ missing_symbol; }", shaderc_glsl_vertex_shader, "invalid" + worker + ".vert", "main", options);
            if (invalid == 0) throw new AssertionError("null error result");
            try {
                if (shaderc_result_get_compilation_status(invalid) == shaderc_compilation_status_success ||
                    !shaderc_result_get_error_message(invalid).contains("missing_symbol"))
                    throw new AssertionError("compiler diagnostics");
            } finally { shaderc_result_release(invalid); }
        } finally { shaderc_compile_options_release(options); shaderc_compiler_release(compiler); }
    }
    public static void main(String[] args) throws Exception {
        compile(-1); // Resolve providers and establish an ordinary compile before contention.
        CountDownLatch ready = new CountDownLatch(4);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread[] threads = new Thread[4];
        for (int index = 0; index < threads.length; ++index) {
            final int worker = index;
            threads[index] = new Thread(() -> {
                try {
                    ready.countDown();
                    if (!ready.await(5, TimeUnit.SECONDS)) throw new AssertionError("thread start timeout");
                    compile(worker);
                } catch (Throwable error) { failure.compareAndSet(null, error); error.printStackTrace(); }
            });
            threads[index].start();
        }
        for (Thread thread : threads) thread.join();
        if (failure.get() != null) throw new AssertionError(failure.get());
        System.out.println("SHADER_NATIVE PASS GLSL SPIR-V reflection diagnostics threads=4");
    }
}
