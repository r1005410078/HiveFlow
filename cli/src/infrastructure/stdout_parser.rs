use serde_json::Value;

use crate::error::AppError;

pub fn parse_json(stdout: &str) -> Result<Value, AppError> {
    serde_json::from_str(stdout).map_err(AppError::InvalidJson)
}
