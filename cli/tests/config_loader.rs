use hf_cli::infrastructure::config_loader::load_config_from;

#[test]
fn load_config_from_file() {
    let content = "server_url = \"http://127.0.0.1:8000\"\ntimeout_ms = 5000\nretry = 2\n";
    let cfg = load_config_from(content).expect("config should parse");
    assert_eq!(cfg.server_url, "http://127.0.0.1:8000");
    assert_eq!(cfg.timeout_ms, 5000);
    assert_eq!(cfg.retry, 2);
}

#[test]
fn load_config_from_invalid_toml() {
    let bad = "server_url = [";
    assert!(load_config_from(bad).is_err());
}
