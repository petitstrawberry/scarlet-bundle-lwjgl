import java.nio.*;
import org.lwjgl.*;
import org.lwjgl.system.*;
import org.lwjgl.vulkan.*;
import org.lwjgl.sdl.*;
import org.lwjgl.util.vma.*;
import static org.lwjgl.util.vma.Vma.*;
import static org.lwjgl.vulkan.VK10.*;
import static org.lwjgl.vulkan.KHRSurface.*;
import static org.lwjgl.vulkan.KHRSwapchain.*;
import static org.lwjgl.sdl.SDLInit.*;
import static org.lwjgl.sdl.SDLVideo.*;
import static org.lwjgl.sdl.SDLVulkan.*;
import static org.lwjgl.sdl.SDLEvents.*;
import static org.lwjgl.sdl.SDLKeyboard.*;
public class SdlGraphicsSmoke {
 static void allocation(VkInstance instance, VkPhysicalDevice physical, VkDevice device) {
  try (MemoryStack stack=MemoryStack.stackPush()) {
   VmaVulkanFunctions functions=VmaVulkanFunctions.calloc(stack).set(instance,device);
   PointerBuffer allocatorPointer=stack.mallocPointer(1), allocation=stack.mallocPointer(1);
   check(vmaCreateAllocator(VmaAllocatorCreateInfo.calloc(stack).physicalDevice(physical).device(device)
      .instance(instance).vulkanApiVersion(VK_MAKE_VERSION(1,1,0)).pVulkanFunctions(functions),allocatorPointer),"VMA allocator");
   long allocator=allocatorPointer.get(0);
   try {
    LongBuffer buffer=stack.mallocLong(1);
    check(vmaCreateBuffer(allocator,VkBufferCreateInfo.calloc(stack).sType$Default().size(4096)
      .usage(VK_BUFFER_USAGE_TRANSFER_SRC_BIT).sharingMode(VK_SHARING_MODE_EXCLUSIVE),
      VmaAllocationCreateInfo.calloc(stack).usage(VMA_MEMORY_USAGE_AUTO)
       .flags(VMA_ALLOCATION_CREATE_HOST_ACCESS_SEQUENTIAL_WRITE_BIT).requiredFlags(VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT),
      buffer,allocation,null),"VMA buffer");
    long memory=allocation.get(0);
    try {
     PointerBuffer mapped=stack.mallocPointer(1);
     check(vmaMapMemory(allocator,memory,mapped),"VMA map");
     try {
      ByteBuffer data=MemoryUtil.memByteBuffer(mapped.get(0),4096);
      for(int i=0;i<data.capacity();i++)data.put(i,(byte)(i*37));
      vmaFlushAllocation(allocator,memory,0,4096);
      vmaInvalidateAllocation(allocator,memory,0,4096);
      for(int i=0;i<data.capacity();i++)if(data.get(i)!=(byte)(i*37))throw new AssertionError("VMA mapped memory");
     } finally {vmaUnmapMemory(allocator,memory);}
    } finally {vmaDestroyBuffer(allocator,buffer.get(0),memory);}
   } finally {vmaDestroyAllocator(allocator);}
   System.out.println("VMA_NATIVE PASS allocate map write flush invalidate free bytes=4096");
  }
 }
 static void check(int r,String op) {if(r!=VK_SUCCESS)throw new AssertionError(op+": "+r);}
 static void require(boolean ok,String op) {if(!ok)throw new AssertionError(op+": "+SDLError.SDL_GetError());}
    static void render(VkDevice device, VkQueue queue, long swapchain, long pool, float red, float green) {
        try (MemoryStack stack = MemoryStack.stackPush()) {
            LongBuffer value = stack.mallocLong(1);
            check(vkCreateFence(device, VkFenceCreateInfo.calloc(stack).sType$Default(), null, value), "fence");
            long fence = value.get(0);
            IntBuffer index = stack.mallocInt(1);
            if (green > red)
                check(vkAcquireNextImage2KHR(device, VkAcquireNextImageInfoKHR.calloc(stack).sType$Default()
                    .swapchain(swapchain).timeout(5_000_000_000L).fence(fence).deviceMask(1), index), "acquire2");
            else check(vkAcquireNextImageKHR(device, swapchain, 5_000_000_000L, 0, fence, index), "acquire");
            check(vkWaitForFences(device, fence, true, 5_000_000_000L), "wait acquire");
            IntBuffer count = stack.mallocInt(1);
            check(vkGetSwapchainImagesKHR(device, swapchain, count, null), "image count");
            LongBuffer images = stack.mallocLong(count.get(0));
            check(vkGetSwapchainImagesKHR(device, swapchain, count, images), "images");
            long image = images.get(index.get(0));
            PointerBuffer pointer = stack.mallocPointer(1);
            check(vkAllocateCommandBuffers(device, VkCommandBufferAllocateInfo.calloc(stack).sType$Default()
                .commandPool(pool).level(VK_COMMAND_BUFFER_LEVEL_PRIMARY).commandBufferCount(1), pointer), "allocate commands");
            VkCommandBuffer command = new VkCommandBuffer(pointer.get(0), device);
            check(vkBeginCommandBuffer(command, VkCommandBufferBeginInfo.calloc(stack).sType$Default()), "begin");
            VkImageMemoryBarrier.Buffer barrier = VkImageMemoryBarrier.calloc(1, stack).sType$Default()
                .oldLayout(VK_IMAGE_LAYOUT_UNDEFINED).newLayout(VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL)
                .srcQueueFamilyIndex(VK_QUEUE_FAMILY_IGNORED).dstQueueFamilyIndex(VK_QUEUE_FAMILY_IGNORED)
                .image(image).dstAccessMask(VK_ACCESS_TRANSFER_WRITE_BIT);
            barrier.subresourceRange().aspectMask(VK_IMAGE_ASPECT_COLOR_BIT).levelCount(1).layerCount(1);
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, null, null, barrier);
            VkClearColorValue color = VkClearColorValue.calloc(stack).float32(0, red).float32(1, green).float32(2, .15f).float32(3, 1f);
            VkImageSubresourceRange.Buffer range = VkImageSubresourceRange.calloc(1, stack)
                .aspectMask(VK_IMAGE_ASPECT_COLOR_BIT).levelCount(1).layerCount(1);
            vkCmdClearColorImage(command, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, color, range);
            barrier.oldLayout(VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL).newLayout(VK_IMAGE_LAYOUT_PRESENT_SRC_KHR)
                .srcAccessMask(VK_ACCESS_TRANSFER_WRITE_BIT).dstAccessMask(0);
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, 0, null, null, barrier);
            check(vkEndCommandBuffer(command), "end");
            check(vkQueueSubmit(queue, VkSubmitInfo.calloc(stack).sType$Default().pCommandBuffers(pointer), 0), "submit");
            check(vkQueueWaitIdle(queue), "idle");
            check(vkQueuePresentKHR(queue, VkPresentInfoKHR.calloc(stack).sType$Default()
                .swapchainCount(1).pSwapchains(stack.longs(swapchain)).pImageIndices(index)), "present");
            vkFreeCommandBuffers(device, pool, command);
            vkDestroyFence(device, fence, null);
        }
    }
    static long swapchain(VkPhysicalDevice physical, VkDevice device, long surface, long old) {
        try (MemoryStack stack = MemoryStack.stackPush()) {
            VkSurfaceCapabilitiesKHR caps = VkSurfaceCapabilitiesKHR.calloc(stack);
            check(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physical, surface, caps), "capabilities");
            LongBuffer result = stack.mallocLong(1);
            check(vkCreateSwapchainKHR(device, VkSwapchainCreateInfoKHR.calloc(stack).sType$Default()
                .surface(surface).minImageCount(Math.max(2, caps.minImageCount())).imageFormat(VK_FORMAT_B8G8R8A8_UNORM)
                .imageColorSpace(VK_COLOR_SPACE_SRGB_NONLINEAR_KHR).imageExtent(caps.currentExtent()).imageArrayLayers(1)
                .imageUsage(VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT)
                .imageSharingMode(VK_SHARING_MODE_EXCLUSIVE).preTransform(VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR)
                .compositeAlpha(VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR).presentMode(VK_PRESENT_MODE_FIFO_KHR)
                .clipped(true).oldSwapchain(old), null, result), "swapchain");
            System.out.println("GRAPHICS extent=" + caps.currentExtent().width() + "x" + caps.currentExtent().height());
            return result.get(0);
        }
    }

 public static void main(String[] args) throws Exception {
  require(SDL_Init(SDL_INIT_VIDEO),"SDL init");
  require("scarlet".equals(SDL_GetCurrentVideoDriver()),"Native SDL video");
  long window=SDL_CreateWindow("Native SDL Vulkan",320,240,SDL_WINDOW_VULKAN|SDL_WINDOW_RESIZABLE);
  require(window!=0,"SDL window");
  require(SDL_RaiseWindow(window),"raise SDL window");
  require(SDL_StartTextInput(window),"start text input");
  try(MemoryStack stack=MemoryStack.stackPush()) {
   IntBuffer top=stack.mallocInt(1),left=stack.mallocInt(1),bottom=stack.mallocInt(1),right=stack.mallocInt(1),w=stack.mallocInt(1),h=stack.mallocInt(1);
   require(SDL_GetWindowBordersSize(window,top,left,bottom,right) && top.get(0)>0,"ScarletUI frame");
   require(SDL_SetWindowBordered(window,false),"remove decoration");
   for(int i=0;i<10;i++){SDL_PumpEvents();Thread.sleep(10);}
   require(SDL_GetWindowBordersSize(window,top,left,bottom,right) && top.get(0)==0,"borderless frame");
   require(SDL_GetWindowSize(window,w,h) && w.get(0)==320 && h.get(0)==240,"borderless preserves content size");
   require(SDL_SetWindowBordered(window,true),"restore decoration");
   for(int i=0;i<10;i++){SDL_PumpEvents();Thread.sleep(10);}
   require(SDL_GetWindowSize(window,w,h) && w.get(0)==320 && h.get(0)==240,"decoration preserves content size");
  }
  try(MemoryStack stack=MemoryStack.stackPush()) {
   PointerBuffer extensions=SDL_Vulkan_GetInstanceExtensions();
   require(extensions!=null && extensions.remaining()==2,"SDL instance extensions");
   VkInstanceCreateInfo info=VkInstanceCreateInfo.calloc(stack).sType$Default()
    .pApplicationInfo(VkApplicationInfo.calloc(stack).sType$Default().apiVersion(VK_MAKE_VERSION(1,1,0)))
    .ppEnabledExtensionNames(extensions);
   PointerBuffer pointer=stack.mallocPointer(1);LongBuffer handle=stack.mallocLong(1);IntBuffer count=stack.mallocInt(1);
   check(vkCreateInstance(info,null,pointer),"instance");VkInstance instance=new VkInstance(pointer.get(0),info);
   check(vkEnumeratePhysicalDevices(instance,count,null),"physical count");require(count.get(0)>0,"physical devices");
   PointerBuffer devices=stack.mallocPointer(count.get(0));check(vkEnumeratePhysicalDevices(instance,count,devices),"physical devices");
   VkPhysicalDevice physical=new VkPhysicalDevice(devices.get(0),instance);
   require(SDL_Vulkan_GetPresentationSupport(instance,physical,0),"SDL presentation support");
   require(SDL_Vulkan_CreateSurface(window,instance,null,handle),"SDL surface");long surface=handle.get(0);
   VkDeviceQueueCreateInfo.Buffer queues=VkDeviceQueueCreateInfo.calloc(1,stack).sType$Default().queueFamilyIndex(0).pQueuePriorities(stack.floats(1f));
   VkDeviceCreateInfo deviceInfo=VkDeviceCreateInfo.calloc(stack).sType$Default().pQueueCreateInfos(queues)
    .ppEnabledExtensionNames(stack.pointers(stack.UTF8(VK_KHR_SWAPCHAIN_EXTENSION_NAME)));
   check(vkCreateDevice(physical,deviceInfo,null,pointer),"device");VkDevice device=new VkDevice(pointer.get(0),physical,deviceInfo);
   allocation(instance,physical,device);
   vkGetDeviceQueue(device,0,0,pointer);VkQueue queue=new VkQueue(pointer.get(0),device);
   check(vkCreateCommandPool(device,VkCommandPoolCreateInfo.calloc(stack).sType$Default().queueFamilyIndex(0),null,handle),"pool");long pool=handle.get(0);
   long chain=swapchain(physical,device,surface,0);
   SDL_Event event=SDL_Event.malloc(stack);
   for(int i=0;i<6;i++){render(device,queue,chain,pool,.8f,.1f);while(SDL_PollEvent(event)){}Thread.sleep(80);}
   require(SDL_SetWindowSize(window,384,256),"SDL resize");
   for(int i=0;i<20;i++){while(SDL_PollEvent(event)){}Thread.sleep(30);}
   long next=swapchain(physical,device,surface,chain);vkDestroySwapchainKHR(device,chain,null);chain=next;
   for(int i=0;i<6;i++){render(device,queue,chain,pool,.1f,.8f);while(SDL_PollEvent(event)){}Thread.sleep(80);}
   System.out.println("SDL_GRAPHICS READY_INPUT");boolean key=false,textInput=false;
   for(int i=0;i<600 && !(key && textInput);i++) {while(SDL_PollEvent(event)){if(event.type()==SDL_EVENT_KEY_DOWN)key=true;if(event.type()==SDL_EVENT_TEXT_INPUT && "a".equals(event.text().textString()))textInput=true;}Thread.sleep(50);}
   require(key && textInput,"native keyboard and text events");
   check(vkDeviceWaitIdle(device),"idle");vkDestroySwapchainKHR(device,chain,null);vkDestroyCommandPool(device,pool,null);vkDestroyDevice(device,null);
   SDL_Vulkan_DestroySurface(instance,surface,null);vkDestroyInstance(instance,null);
  }
  SDL_DestroyWindow(window);SDL_Quit();
  System.out.println("SDL_GRAPHICS PASS window surface swapchain resize input destroy");
 }
}
