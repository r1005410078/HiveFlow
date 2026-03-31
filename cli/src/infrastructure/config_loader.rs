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

pub fn load_default_config() -> Result<CliConfig, AppError> {
    let home = dirs::home_dir()
        .ok_or_else(|| AppError::Config("home directory is unavailable".to_string()))?;
    let path = home.join(".hiveflow").join("config.toml");
    let raw = std::fs::read_to_string(path).map_err(AppError::ConfigIo)?;
    load_config_from(&raw).map_err(AppError::ConfigParse)
}
