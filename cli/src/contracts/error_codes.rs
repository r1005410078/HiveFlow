#[derive(Debug, Clone)]
pub enum ErrorCode {
    ConfigError,
    TransportError,
    UpstreamError,
    InvalidJson,
    InvalidArgs,
}

impl ErrorCode {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::ConfigError => "CONFIG_ERROR",
            Self::TransportError => "TRANSPORT_ERROR",
            Self::UpstreamError => "UPSTREAM_ERROR",
            Self::InvalidJson => "INVALID_JSON",
            Self::InvalidArgs => "INVALID_ARGUMENT",
        }
    }
}
