fn main() {
    println!("GRAPHICS_GUEST start");
    let result: usize;
    unsafe {
        core::arch::asm!("svc #0", inout("x0") 3usize => result,
            in("x1") c"/tmp".as_ptr(), in("x2") c"tmpfs".as_ptr(),
            in("x3") c"size=128M".as_ptr(), in("x8") 524usize, clobber_abi("C"));
    }
    assert_ne!(result, usize::MAX, "mount test state");
    let sdl = std::fs::read_to_string("/app/graphics-binding").expect("binding") == "sdl";
    let smoke = if sdl { "SdlGraphicsSmoke" } else { "GraphicsSmoke" };
    let classpath = if sdl {
        "/app/lwjgl.jar:/app/lwjgl-sdl.jar:/app/lwjgl-vulkan.jar:/app/lwjgl-vma.jar:/app/classes"
    } else { "/app/lwjgl.jar:/app/lwjgl-glfw.jar:/app/lwjgl-vulkan.jar:/app/classes" };
    let compile = format!("-XX:CompileCommand=compileonly,{smoke}::*");
    let _bus = std::process::Command::new("/bin/sbusd").spawn().expect("sbusd");
    std::thread::sleep(std::time::Duration::from_millis(200));
    let mut sws = std::process::Command::new("/bin/sws").env("SWS_BACKEND", "sgfx").spawn().expect("sws");
    std::thread::sleep(std::time::Duration::from_secs(7));
    println!("GRAPHICS_GUEST sws={:?}", sws.try_wait());
    let status = std::process::Command::new("/bin/java")
        .args(["-Xms128m", "-Xmx768m", "-Xcheck:jni", "-Xcomp", "-XX:-BackgroundCompilation", "-XX:CompilationMode=high-only", "-XX:+PrintCompilation",
            &compile, "-XX:ErrorFile=/tmp/jvm-error.log", "--enable-native-access=ALL-UNNAMED",
            "-Dorg.lwjgl.librarypath=/app/native", "-Dorg.lwjgl.system.allocator=system",
            "-Dorg.lwjgl.util.Debug=true", "-Dorg.lwjgl.vulkan.libname=/lib/libvulkan.so.1",
            "-cp", classpath, smoke])
        .env("VK_DRIVER_FILES", "/share/vulkan/icd.d/sgfx.json")
        .status();
    println!("GRAPHICS_GUEST java={status:?}");
    if let Ok(log) = std::fs::read_to_string("/tmp/jvm-error.log") { println!("{log}"); }
    println!("GRAPHICS_GUEST {}", if status.is_ok_and(|s| s.success()) { "PASS" } else { "FAIL" });
    unsafe { core::arch::asm!("svc #0", inout("x0") 0usize => _, inout("x1") 0usize => _, inout("x8") 1000usize => _, clobber_abi("C")); }
}
