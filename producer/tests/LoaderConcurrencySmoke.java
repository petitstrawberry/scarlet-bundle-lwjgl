import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.lwjgl.system.scarlet.ScarletLibrary;

public class LoaderConcurrencySmoke {
    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(4);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread[] workers = new Thread[4];
        for (int index = 0; index < workers.length; ++index) {
            final int id = index;
            workers[index] = new Thread(() -> {
                try {
                    ready.countDown();
                    if (!ready.await(5, TimeUnit.SECONDS)) throw new AssertionError("startup timeout");
                    for (int attempt = 0; attempt < 32; ++attempt) {
                        String path = "/lib/scarlet-loader-missing-" + id + "-" + attempt + ".so";
                        try {
                            new ScarletLibrary(path).free();
                            throw new AssertionError("unexpected library: " + path);
                        } catch (UnsatisfiedLinkError expected) {
                            String message = expected.getMessage();
                            // The prefix contains the requested path; verify the
                            // loader's parenthesized error independently.
                            String detail = message.substring(message.indexOf(" (") + 2);
                            if (!detail.contains(path) || detail.contains("busy"))
                                throw new AssertionError("wrong thread's loader error: " + detail);
                        }
                    }
                } catch (Throwable error) { failure.compareAndSet(null, error); }
            });
            workers[index].setDaemon(true);
            workers[index].start();
        }
        for (Thread worker : workers) {
            worker.join(15000);
            if (worker.isAlive()) throw new AssertionError("loader thread timeout");
        }
        if (failure.get() != null) throw new AssertionError(failure.get());
        System.out.println("LOADER_CONCURRENCY PASS threads=4 errors=128");
    }
}
