#include <pthread.h>
#include <stdint.h>
__attribute__((visibility("default"))) int lwjgl_probe_add(int a, int b) { return a + b; }
struct Invocation { int (*callback)(int); int value; int result; };
static void *invoke(void *argument) {
    struct Invocation *call = argument;
    call->result = call->callback(call->value);
    return 0;
}
__attribute__((visibility("default"))) int lwjgl_probe_callback_thread(int (*callback)(int), int value) {
    struct Invocation call = {callback, value, 0};
    pthread_t thread;
    if (pthread_create(&thread, 0, invoke, &call) != 0) return -1;
    if (pthread_join(thread, 0) != 0) return -2;
    return call.result;
}
