use crate::contracts::error_codes::ErrorCode;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("config error: {0}")]
    Config(String),
    #[error("config io error: {0}")]
    ConfigIo(std::io::Error),
    #[error("config parse error: {0}")]
    ConfigParse(toml::de::Error),
    #[error("http client error: {0}")]
    HttpClient(reqwest::Error),
    #[error("upstream service returned status {0}: {1}")]
    Upstream(u16, serde_json::Value),
    #[error("invalid json from python: {0}")]
    InvalidJson(serde_json::Error),
    #[error("invalid args: {0}")]
    InvalidArgs(String),
}

impl AppError {
    pub fn code(&self) -> ErrorCode {
        match self {
            Self::Config(_) | Self::ConfigIo(_) | Self::ConfigParse(_) => ErrorCode::ConfigError,
            Self::HttpClient(_) => ErrorCode::TransportError,
            Self::Upstream(_, _) => ErrorCode::UpstreamError,
            Self::InvalidJson(_) => ErrorCode::InvalidJson,
            Self::InvalidArgs(_) => ErrorCode::InvalidArgs,
        }
    }
}
