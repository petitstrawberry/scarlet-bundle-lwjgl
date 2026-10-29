import java.nio.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.lwjgl.stb.*;
import org.lwjgl.system.*;
public class StbSmoke {
 public static void main(String[] args) throws Exception {
  byte[] png=java.util.Base64.getDecoder().decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAACCAYAAACZgbYnAAAAEUlEQVR4nGP4z8AARAz//wMAEfgD/XUCLkgAAAAASUVORK5CYII=");
  System.out.println("STB stage=library-init");
  STBImage.stbi_set_flip_vertically_on_load(false);
  System.out.println("STB stage=threads");
  CountDownLatch start=new CountDownLatch(4);AtomicReference<Throwable> failure=new AtomicReference<>();
  Thread[] workers=new Thread[4];
  for(int n=0;n<workers.length;n++) {final boolean flip=(n&1)!=0;workers[n]=new Thread(()->{
   ByteBuffer input=MemoryUtil.memAlloc(png.length).put(png).flip();
   try(MemoryStack stack=MemoryStack.stackPush()) {
    STBImage.stbi_set_flip_vertically_on_load_thread(flip?1:0);System.out.println("STB thread flags="+flip);start.countDown();if(!start.await(5,TimeUnit.SECONDS))throw new AssertionError("thread startup timeout");
    IntBuffer x=stack.mallocInt(1),y=stack.mallocInt(1),channels=stack.mallocInt(1);
    for(int i=0;i<30;i++) {
     ByteBuffer pixels=STBImage.stbi_load_from_memory(input,x,y,channels,4);
     if(pixels==null)throw new AssertionError(STBImage.stbi_failure_reason());
     try {if(x.get(0)!=1 || y.get(0)!=2 || (pixels.get(0)&255)!=(flip?0:255) || (pixels.get(2)&255)!=(flip?255:0))throw new AssertionError("thread-local PNG orientation");}
     finally{STBImage.stbi_image_free(pixels);}
    }
   }catch(Throwable t){failure.compareAndSet(null,t);t.printStackTrace();start.countDown();}finally{MemoryUtil.memFree(input);}
  });workers[n].start();}
  for(Thread worker:workers)worker.join();
  if(failure.get()!=null)throw new AssertionError(failure.get());
  System.out.println("STB_NATIVE PASS PNG decode flip isolation threads=4");
 }
}
