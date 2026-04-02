use mockito::Server;

#[test]
fn data_bars_tui_falls_back_when_tui_is_unavailable() {
    let mut server = Server::new();
    let _mock = server
        .mock("GET", "/v1/market-data/bars")
        .match_query(mockito::Matcher::AllOf(vec![
            mockito::Matcher::UrlEncoded("symbols".into(), "600519.SH".into()),
            mockito::Matcher::UrlEncoded("timeframe".into(), "1d".into()),
        ]))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"symbol":"600519.SH","timeframe":"1d","bar_time":"2026-04-01T15:00:00+08:00","open":1450.0,"high":1468.0,"low":1442.0,"close":1459.44,"volume":29125.0,"amount":4256185472.0,"data_source":"tencent"}]}"#,
        )
        .create();

    let unique = format!(
        "hf-cli-bars-tui-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system time before epoch")
            .as_nanos()
    );
    let fake_home = std::env::temp_dir().join(unique);
    let config_dir = fake_home.join(".hiveflow");
    std::fs::create_dir_all(&config_dir).expect("create config dir");
    std::fs::write(
        config_dir.join("config.toml"),
        format!("server_url = {:?}\ntimeout_ms = 1000\nretry = 1\n", server.url()),
    )
    .expect("write config");

    let output = std::process::Command::new("cargo")
        .args([
            "run",
            "--quiet",
            "--",
            "data",
            "bars",
            "--symbols",
            "600519.SH",
            "--timeframe",
            "1d",
            "--output",
            "tui",
        ])
        .current_dir(".")
        .env("HOME", &fake_home)
        .output()
        .expect("run cli data bars tui");

    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("warning: tui output unavailable"),
        "stderr did not show tui fallback: {stderr}"
    );
    assert!(
        stdout.contains("Price Chart (textplots)") || stdout.contains("Market Data"),
        "stdout did not show chart/table fallback: {stdout}"
    );
}
