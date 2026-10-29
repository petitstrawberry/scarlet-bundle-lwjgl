fn main() {
    let mut passed = true;
    for mode in ["-Xint", "-Xcomp"] {
        let status = std::process::Command::new("/bin/java")
            .args([mode, "-XX:-BackgroundCompilation", "-XX:CompilationMode=high-only", "-XX:+PrintCompilation",
                "-XX:CompileCommand=compileonly,LwjglSmoke::*",
                "-XX:CompileCommand=compileonly,LwjglSmoke$DoubleCallback::*", "-XX:ErrorFile=/tmp/jvm-error.log",
                "--enable-native-access=ALL-UNNAMED", "-Dorg.lwjgl.librarypath=/app/native", "-Dorg.lwjgl.system.allocator=system",
                "-Dorg.lwjgl.util.Debug=true", "-cp", "/app/lwjgl.jar:/app/classes", "LwjglSmoke"])
            .status();
        match status {
            Ok(exit) if exit.success() => println!("LWJGL_GUEST {mode} exit=0"),
            other => { passed = false; println!("LWJGL_GUEST FAIL {mode} {other:?}"); }
        }
        if let Ok(log) = std::fs::read_to_string("/tmp/jvm-error.log") { println!("{log}"); }
        if !passed { break; }
    }
    println!("LWJGL_GUEST {}", if passed { "PASS" } else { "FAIL" });
    unsafe {
        core::arch::asm!("svc #0", inout("x0") 0usize => _, inout("x1") 0usize => _,
                        inout("x8") 1000usize => _, clobber_abi("C"));
    }
    std::process::exit(1);
}
