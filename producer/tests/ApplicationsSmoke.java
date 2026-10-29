public class ApplicationsSmoke {
    public static void main(String[] args) throws Exception {
        SdlLoadSmoke.main(args);
        StbSmoke.main(args);
        FreeTypeSmoke.main(args);
        ShaderSmoke.main(args);
        OpenALSmoke.main(args);
        OpenGLLoadSmoke.main(args);
        Class.forName("org.lwjgl.util.vma.Vma");
        System.out.println("VMA_LOAD PASS");
        System.out.println("APPLICATION_MODULES PASS");
    }
}
