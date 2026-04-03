#[test]
fn hf_cli_build_has_no_dead_code_warnings() {
    let output = std::process::Command::new("cargo")
        .args(["build", "--bin", "hf-cli"])
        .current_dir(".")
        .env("RUSTFLAGS", "-Dwarnings")
        .output()
        .expect("run cargo build with warnings denied");

    assert!(
        output.status.success(),
        "expected warning-free build, got:\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}
