import org.lwjgl.opengl.GL;
public class OpenGLLoadSmoke {
    public static void main(String[] args) {
        if (GL.getFunctionProvider().getFunctionAddress("glGetString") == 0)
            throw new AssertionError("OpenGL dispatch function missing");
        boolean rejected = false;
        try { GL.createCapabilities(); }
        catch (IllegalStateException expected) {
            if (!expected.getMessage().contains("context")) throw expected;
            rejected = true;
        }
        if (!rejected) throw new AssertionError("contextless OpenGL was accepted");
        GL.destroy();
        System.out.println("OPENGL_DISPATCH PASS provider loaded no-context rejected");
    }
}
