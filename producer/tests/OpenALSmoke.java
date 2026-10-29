import java.nio.*;
import org.lwjgl.openal.*;
import org.lwjgl.system.MemoryStack;
import static org.lwjgl.openal.AL10.*;
import static org.lwjgl.openal.ALC10.*;
import static org.lwjgl.openal.SOFTLoopback.*;
public class OpenALSmoke {
    public static void main(String[] args) {
        long device = alcLoopbackOpenDeviceSOFT((ByteBuffer)null);
        if (device == 0) throw new AssertionError("loopback device");
        try (MemoryStack stack = MemoryStack.stackPush()) {
            if (!alcIsRenderFormatSupportedSOFT(device,48000,ALC_STEREO_SOFT,ALC_SHORT_SOFT))
                throw new AssertionError("PCM format");
            IntBuffer attributes = stack.ints(ALC_FREQUENCY,48000,ALC_FORMAT_CHANNELS_SOFT,ALC_STEREO_SOFT,
                ALC_FORMAT_TYPE_SOFT,ALC_SHORT_SOFT,0);
            long context = alcCreateContext(device,attributes);
            if (context == 0) throw new AssertionError("context error="+alcGetError(device));
            try {
                if (!alcMakeContextCurrent(context)) throw new AssertionError("current context");
                AL.createCapabilities(ALC.createCapabilities(device));
                int buffer = alGenBuffers(), source = alGenSources();
                try {
                    ShortBuffer pcm = stack.mallocShort(4800);
                    for (int index=0;index<pcm.capacity();index++)
                        pcm.put(index,(short)(Math.sin(2*Math.PI*440*index/48000)*16000));
                    alBufferData(buffer,AL_FORMAT_MONO16,pcm,48000);
                    alSourcei(source,AL_BUFFER,buffer);
                    alSourcePlay(source);
                    ShortBuffer rendered = stack.callocShort(2048);
                    alcRenderSamplesSOFT(device,rendered,1024);
                    if (alGetError()!=AL_NO_ERROR || alcGetError(device)!=ALC_NO_ERROR)
                        throw new AssertionError("mix error");
                    int nonzero=0,peak=0;
                    for(int index=0;index<rendered.capacity();index++) {
                        int value=Math.abs((int)rendered.get(index));
                        if(value!=0)++nonzero;
                        peak=Math.max(peak,value);
                    }
                    if(nonzero<1000 || peak<1000) throw new AssertionError("silent PCM mix");
                    alSourcei(source,0x7fffffff,0);
                    if(alGetError()!=AL_INVALID_ENUM) throw new AssertionError("OpenAL error reporting");
                    System.out.println("OPENAL_NATIVE PASS loopback PCM frames=1024 nonzero="+nonzero+" peak="+peak);
                } finally {alDeleteSources(source);alDeleteBuffers(buffer);}
            } finally {alcMakeContextCurrent(0);alcDestroyContext(context);}
        } finally {if(!alcCloseDevice(device))throw new AssertionError("close device");}
    }
}
