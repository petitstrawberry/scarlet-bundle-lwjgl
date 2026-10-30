fn main() {
    let result: usize;
    unsafe {
        core::arch::asm!("svc #0", inout("x0") 3usize => result,
            in("x1") c"/tmp".as_ptr(), in("x2") c"tmpfs".as_ptr(),
            in("x3") c"size=128M".as_ptr(), in("x8") 524usize, clobber_abi("C"));
    }
    assert_ne!(result, usize::MAX, "mount test state");
    let arguments = std::fs::read_to_string("/app/java-arguments").expect("Java arguments");
    let status = std::process::Command::new("/bin/java")
        .current_dir("/tmp").args(arguments.split_terminator('\n')).status();
    println!("APPLICATION_MODULES_GUEST {} {status:?}",
        if status.as_ref().is_ok_and(|value| value.success()) { "PASS" } else { "FAIL" });
    unsafe {
        core::arch::asm!("svc #0", inout("x0") 0usize => _, inout("x1") 0usize => _,
            inout("x8") 1000usize => _, clobber_abi("C"));
    }
}
