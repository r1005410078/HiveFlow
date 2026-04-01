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
