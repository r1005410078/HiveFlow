#[test]
fn hf_help_works() {
    let output = std::process::Command::new("cargo")
        .args(["run", "--", "--help"])
        .current_dir(".")
        .output()
        .expect("run cli help");
    assert!(output.status.success());
}

#[test]
fn pipeline_daily_fails_without_config_file() {
    let unique = format!(
        "hf-cli-smoke-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system time before epoch")
            .as_nanos()
    );
    let fake_home = std::env::temp_dir().join(unique);
    std::fs::create_dir_all(&fake_home).expect("create fake home");

    let output = std::process::Command::new("cargo")
        .args(["run", "--", "pipeline", "daily", "--as-of", "2026-04-01"])
        .current_dir(".")
        .env("HOME", &fake_home)
        .output()
        .expect("run cli pipeline daily");

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("config.toml") || stderr.contains("config io error"),
        "stderr did not mention missing config: {stderr}"
    );
}
