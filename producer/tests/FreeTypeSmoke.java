import java.nio.ByteBuffer;
import org.lwjgl.PointerBuffer;
import org.lwjgl.system.MemoryStack;
import org.lwjgl.util.freetype.*;
import static org.lwjgl.util.freetype.FreeType.*;

public class FreeTypeSmoke {
    private static void check(int result, String operation) {
        if (result != 0) throw new AssertionError(operation + " error=" + result);
    }
    public static void main(String[] args) {
        try (MemoryStack stack = MemoryStack.stackPush()) {
            PointerBuffer pointer = stack.mallocPointer(1);
            check(FT_Init_FreeType(pointer), "init");
            long library = pointer.get(0);
            try {
                check(FT_New_Face(library, "/app/font.ttf", 0, pointer), "open font");
                FT_Face face = FT_Face.create(pointer.get(0));
                try {
                    check(FT_Set_Pixel_Sizes(face, 0, 24), "size");
                    check(FT_Load_Char(face, 'A', FT_LOAD_RENDER), "render");
                    FT_Bitmap bitmap = face.glyph().bitmap();
                    int size = Math.abs(bitmap.pitch()) * bitmap.rows();
                    ByteBuffer pixels = bitmap.buffer(size);
                    if (bitmap.width() < 4 || bitmap.rows() < 4 || pixels == null)
                        throw new AssertionError("empty glyph bitmap");
                    int nonzero = 0;
                    for (int index = 0; index < size; ++index) if (pixels.get(index) != 0) ++nonzero;
                    if (nonzero < 10) throw new AssertionError("blank raster");
                    System.out.println("FREETYPE_NATIVE PASS glyph=A width=" + bitmap.width() +
                        " rows=" + bitmap.rows() + " coverage=" + nonzero);
                } finally { check(FT_Done_Face(face), "close face"); }
            } finally { check(FT_Done_FreeType(library), "close library"); }
        }
    }
}
