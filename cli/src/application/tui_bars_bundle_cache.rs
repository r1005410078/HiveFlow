//! `POST /v1/market-data/bars-bundle` 响应在 `hf tui` 中的内存缓存（按 timeframe 分桶）。

use std::collections::HashMap;

use serde_json::{json, Value};

use crate::error::AppError;

/// 已拉齐的多周期 bars（items 行与 `GET /bars` 一致）；标的由外层 `HashMap` 的 key 标识。
pub struct TuiBarsBundleCache {
    by_timeframe: HashMap<String, Vec<Value>>,
    /// 记忆化存储：按 timeframe 存储已经过中文名注入、OHLC 聚合以及 `serde_json::json!` 序列化好的最终 TUI payload。
    memoized_aggregated: std::sync::Arc<std::sync::RwLock<HashMap<String, Value>>>,
}

impl TuiBarsBundleCache {
    pub fn from_bundle_response(body: &Value) -> Result<Self, AppError> {
        let by_tf = body
            .get("by_timeframe")
            .and_then(Value::as_object)
            .ok_or_else(|| AppError::InvalidArgs("bars-bundle 响应缺少 by_timeframe".into()))?;
        let mut map = HashMap::new();
        for (tf, block) in by_tf {
            let items = block
                .get("items")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            map.insert(tf.clone(), items);
        }
        Ok(Self {
            by_timeframe: map,
            memoized_aggregated: std::sync::Arc::new(std::sync::RwLock::new(HashMap::new())),
        })
    }

    pub fn raw_payload_for_timeframe(&self, tf: &str) -> Value {
        let items = self
            .by_timeframe
            .get(tf)
            .cloned()
            .unwrap_or_default();
        json!({ "items": items })
    }

    /// 获取针对 TUI 展示已完成聚合的记忆化数据。
    pub fn get_memoized_tui_payload(&self, tf: &str) -> Option<Value> {
        self.memoized_aggregated.read().ok()?.get(tf).cloned()
    }

    /// 存入针对 TUI 展示已完成聚合的数据。
    pub fn set_memoized_tui_payload(&self, tf: &str, payload: Value) {
        if let Ok(mut lock) = self.memoized_aggregated.write() {
            lock.insert(tf.to_string(), payload);
        }
    }

    /// 当前周期桶内 bar 行数（用于拒绝用空 SWR 结果覆盖仍有 K 线的缓存）。
    pub fn item_count_for_timeframe(&self, tf: &str) -> usize {
        self.by_timeframe.get(tf).map(|v| v.len()).unwrap_or(0)
    }
}
