use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Serialize, Deserialize)]
pub struct CliOutput {
    pub schema_version: String,
    pub command: String,
    pub run_id: String,
    pub status: String,
    pub generated_at: String,
    pub source: String,
    pub advice_only: bool,
    pub decision_weight: i64,
    pub data: Value,
    pub warnings: Vec<Value>,
    pub errors: Vec<Value>,
}
