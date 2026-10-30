import org.lwjgl.sdl.*;
public class SdlLoadSmoke {
    public static void main(String[] args) {
        String platform = SDLPlatform.SDL_GetPlatform();
        int version = SDLVersion.SDL_GetVersion();
        if (!"Scarlet".equals(platform) || version < 3004000) throw new AssertionError("SDL platform/version");
        if (!SDLInit.SDL_Init(0)) throw new AssertionError(SDLError.SDL_GetError());
        SDLInit.SDL_Quit();
        System.out.println("SDL_LOAD PASS platform=" + platform + " version=" + version);
    }
}
