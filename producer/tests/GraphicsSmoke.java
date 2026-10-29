import java.nio.*;
import org.lwjgl.PointerBuffer;
import org.lwjgl.glfw.*;
import org.lwjgl.system.*;
import org.lwjgl.vulkan.*;
import static org.lwjgl.glfw.GLFW.*;
import static org.lwjgl.glfw.GLFWVulkan.*;
import static org.lwjgl.vulkan.VK10.*;
import static org.lwjgl.vulkan.KHRSurface.*;
import static org.lwjgl.vulkan.KHRSwapchain.*;

public class GraphicsSmoke {
    static void check(int result, String operation) {
        if (result != VK_SUCCESS) throw new AssertionError(operation + ": " + result);
    }
    static void require(boolean ok, String message) { if (!ok) throw new AssertionError(message); }
    static int keys, sizes, characters;
    static int initialFramebufferWidth;
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
    static void verifyFrame(long window, boolean decorated, int width, int height) {
        try (MemoryStack stack = MemoryStack.stackPush()) {
            IntBuffer w=stack.mallocInt(1), h=stack.mallocInt(1);
            IntBuffer left=stack.mallocInt(1), top=stack.mallocInt(1), right=stack.mallocInt(1), bottom=stack.mallocInt(1);
            glfwGetWindowSize(window,w,h);
            require(w.get(0)==width && h.get(0)==height,"logical content extent");
            glfwGetWindowFrameSize(window,left,top,right,bottom);
            require(decorated ? top.get(0)>0 : (left.get(0)|top.get(0)|right.get(0)|bottom.get(0))==0,"frame insets");
            FloatBuffer sx=stack.mallocFloat(1), sy=stack.mallocFloat(1);
            glfwGetWindowContentScale(window,sx,sy);
            glfwGetFramebufferSize(window,w,h);
            require(w.get(0)==(int)Math.ceil(width*sx.get(0)) && h.get(0)==(int)Math.ceil(height*sy.get(0)),"physical content extent");
            initialFramebufferWidth=w.get(0);
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
        GLFWErrorCallback errors = GLFWErrorCallback.createPrint(System.err).set();
        require(glfwInit(), "glfwInit");
        require(glfwGetPlatform() == GLFW_PLATFORM_SCARLET, "Scarlet platform");
        glfwWindowHint(GLFW_CLIENT_API, GLFW_NO_API);
        long window = glfwCreateWindow(320, 240, "LWJGL Vulkan", 0, 0);
        require(window != 0, "window");
        verifyFrame(window,true,320,240);
        glfwSetWindowAttrib(window,GLFW_DECORATED,GLFW_FALSE);
        verifyFrame(window,false,320,240);
        glfwSetWindowAttrib(window,GLFW_DECORATED,GLFW_TRUE);
        verifyFrame(window,true,320,240);
        glfwSetWindowAttrib(window,GLFW_RESIZABLE,GLFW_FALSE);
        glfwSetWindowAttrib(window,GLFW_RESIZABLE,GLFW_TRUE);
        glfwSetWindowTitle(window,"ScarletUI Vulkan window");
        System.out.println("GRAPHICS frame toggles and content scale PASS");
        GLFWKeyCallback key = GLFWKeyCallback.create((w, k, scan, action, mods) -> { if (k == GLFW_KEY_A && action == GLFW_PRESS) keys++; });
        GLFWFramebufferSizeCallback size = GLFWFramebufferSizeCallback.create((w, x, y) -> sizes++);
        GLFWCharCallback text = GLFWCharCallback.create((w, codepoint) -> { if (codepoint == 'a') characters++; });
        glfwSetCharCallback(window, text);
        glfwSetKeyCallback(window, key); glfwSetFramebufferSizeCallback(window, size);
        require(glfwVulkanSupported(), "Vulkan loader");
        try (MemoryStack stack = MemoryStack.stackPush()) {
            PointerBuffer extensions = glfwGetRequiredInstanceExtensions();
            require(extensions != null && extensions.remaining() == 2, "surface extensions");
            System.out.println("GRAPHICS extensions=" + extensions.getStringUTF8(0) + "," + extensions.getStringUTF8(1));
            VkInstanceCreateInfo info = VkInstanceCreateInfo.calloc(stack).sType$Default()
                .pApplicationInfo(VkApplicationInfo.calloc(stack).sType$Default().apiVersion(VK_MAKE_VERSION(1, 1, 0)))
                .ppEnabledExtensionNames(extensions);
            PointerBuffer pointer = stack.mallocPointer(1);
            check(vkCreateInstance(info, null, pointer), "instance");
            VkInstance instance = new VkInstance(pointer.get(0), info);
            IntBuffer count = stack.mallocInt(1);
            check(vkEnumeratePhysicalDevices(instance, count, null), "physical count");
            require(count.get(0) > 0, "physical device");
            PointerBuffer devices = stack.mallocPointer(count.get(0));
            check(vkEnumeratePhysicalDevices(instance, count, devices), "physical devices");
            VkPhysicalDevice physical = new VkPhysicalDevice(devices.get(0), instance);
            require(glfwGetPhysicalDevicePresentationSupport(instance, physical, 0), "presentation support");
            LongBuffer handle = stack.mallocLong(1);
            check(glfwCreateWindowSurface(instance, window, null, handle), "surface"); long surface = handle.get(0);
            VkDeviceQueueCreateInfo.Buffer queues = VkDeviceQueueCreateInfo.calloc(1, stack).sType$Default().queueFamilyIndex(0).pQueuePriorities(stack.floats(1f));
            VkDeviceCreateInfo deviceInfo = VkDeviceCreateInfo.calloc(stack).sType$Default().pQueueCreateInfos(queues)
                .ppEnabledExtensionNames(stack.pointers(stack.UTF8(VK_KHR_SWAPCHAIN_EXTENSION_NAME)));
            check(vkCreateDevice(physical, deviceInfo, null, pointer), "device");
            VkDevice device = new VkDevice(pointer.get(0), physical, deviceInfo);
            require(device.getCapabilities().VK_KHR_swapchain, "complete swapchain entry points");
            VkDeviceGroupPresentCapabilitiesKHR group = VkDeviceGroupPresentCapabilitiesKHR.calloc(stack).sType$Default();
            check(vkGetDeviceGroupPresentCapabilitiesKHR(device, group), "present group");
            require(group.presentMask(0) == 1 && group.modes() == VK_DEVICE_GROUP_PRESENT_MODE_LOCAL_BIT_KHR, "single device group");
            IntBuffer modes = stack.mallocInt(1);
            check(vkGetDeviceGroupSurfacePresentModesKHR(device, surface, modes), "present modes");
            require(modes.get(0) == VK_DEVICE_GROUP_PRESENT_MODE_LOCAL_BIT_KHR, "local present");
            check(vkGetPhysicalDevicePresentRectanglesKHR(physical, surface, count, null), "rectangle count");
            require(count.get(0) == 1, "one rectangle");
            VkRect2D.Buffer rectangles = VkRect2D.calloc(1, stack);
            check(vkGetPhysicalDevicePresentRectanglesKHR(physical, surface, count, rectangles), "rectangles");
            require(rectangles.get(0).extent().width() == initialFramebufferWidth, "rectangle width");
            vkGetDeviceQueue(device, 0, 0, pointer); VkQueue queue = new VkQueue(pointer.get(0), device);
            check(vkCreateCommandPool(device, VkCommandPoolCreateInfo.calloc(stack).sType$Default().queueFamilyIndex(0), null, handle), "pool");
            long pool = handle.get(0), chain = swapchain(physical, device, surface, 0);
            for (int i = 0; i < 6; i++) {
                render(device, queue, chain, pool, .8f, .1f);
                glfwSetWindowTitle(window,"Frame repaint " + i);
                glfwPollEvents(); Thread.sleep(80);
            }
            glfwSetWindowSize(window, 384, 256);
            for (int i = 0; i < 10; i++) { glfwPollEvents(); Thread.sleep(30); }
            check(vkCreateFence(device, VkFenceCreateInfo.calloc(stack).sType$Default(), null, handle), "resize fence");
            long resizeFence = handle.get(0);
            require(vkAcquireNextImageKHR(device, chain, 0, 0, resizeFence, count) == VK_ERROR_OUT_OF_DATE_KHR,
                "old swapchain is out of date after resize");
            vkDestroyFence(device, resizeFence, null);
            long replacement = swapchain(physical, device, surface, chain);
            vkDestroySwapchainKHR(device, chain, null); chain = replacement;
            for (int i = 0; i < 8; i++) { render(device, queue, chain, pool, .1f, .8f); glfwPollEvents(); Thread.sleep(80); }
            require(sizes > 0, "resize callback");
            System.out.println("GRAPHICS READY_INPUT");
            for (int i = 0; i < 1200 && keys == 0; i++) glfwWaitEventsTimeout(.05);
            require(keys > 0 && characters > 0, "key and text callbacks");
            check(vkDeviceWaitIdle(device), "device idle");
            vkDestroySwapchainKHR(device, chain, null); vkDestroyCommandPool(device, pool, null);
            vkDestroyDevice(device, null); vkDestroySurfaceKHR(instance, surface, null); vkDestroyInstance(instance, null);
            IntBuffer width = stack.mallocInt(1), height = stack.mallocInt(1);
            glfwGetWindowSize(window, width, height);
            require(width.get(0) == 384 && height.get(0) == 256, "surface destruction preserves the GLFW window");
            verifyFrame(window,true,384,256);
            long monitor=glfwGetPrimaryMonitor();
            GLFWVidMode mode=glfwGetVideoMode(monitor);
            glfwSetWindowMonitor(window,monitor,0,0,mode.width(),mode.height(),GLFW_DONT_CARE);
            for (int i=0;i<10;i++) { glfwPollEvents(); Thread.sleep(20); }
            IntBuffer l=stack.mallocInt(1), t=stack.mallocInt(1), r=stack.mallocInt(1), b=stack.mallocInt(1);
            glfwGetWindowFrameSize(window,l,t,r,b);
            require((l.get(0)|t.get(0)|r.get(0)|b.get(0))==0,"fullscreen has no chrome");
            glfwGetFramebufferSize(window,width,height);
            require(width.get(0)==mode.width() && height.get(0)==mode.height(),"fullscreen framebuffer extent");
            glfwSetWindowMonitor(window,0,0,0,384,256,GLFW_DONT_CARE);
            for (int i=0;i<10;i++) { glfwPollEvents(); Thread.sleep(20); }
            verifyFrame(window,true,384,256);
            System.out.println("GRAPHICS fullscreen restore PASS");
        }
        glfwDestroyWindow(window); glfwTerminate(); key.free(); size.free(); text.free(); errors.free();
        System.out.println("GRAPHICS PASS windows resize input swapchain present destroy");
    }
}
