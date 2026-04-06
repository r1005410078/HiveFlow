use std::path::PathBuf;

use serde::Deserialize;

use crate::error::AppError;

#[derive(Debug, Clone, Deserialize)]
pub struct CliConfig {
    pub server_url: String,
    pub timeout_ms: u64,
    pub retry: u32,
}

pub fn load_config_from(raw: &str) -> Result<CliConfig, toml::de::Error> {
    toml::from_str(raw)
}

/// `~/.hiveflow/config.toml`（不校验存在性）。
pub fn default_config_path() -> Result<PathBuf, AppError> {
    let home = dirs::home_dir()
        .ok_or_else(|| AppError::Config("home directory is unavailable".to_string()))?;
    Ok(home.join(".hiveflow").join("config.toml"))
}

pub fn load_default_config() -> Result<CliConfig, AppError> {
    let path = default_config_path()?;
    let raw = std::fs::read_to_string(path).map_err(AppError::ConfigIo)?;
    let cfg = load_config_from(&raw).map_err(AppError::ConfigParse)?;
    // Keep retry in the runtime contract even if handlers do not yet apply retry policy.
    let _configured_retry = cfg.retry;
    Ok(cfg)
}
