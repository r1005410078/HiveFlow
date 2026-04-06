use serde_json::{json, Value};

use crate::application::requests::DoctorRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::{default_config_path, load_config_from};
use crate::infrastructure::http_client::{get_system_doctor, probe_openapi_json, OpenapiProbeOutcome};
use crate::infrastructure::table_renderer::render_doctor_table;

const COMMAND: &str = "hf doctor";

pub fn handle(args: DoctorRequest) -> Result<(), AppError> {
    let envelope = build_envelope(&args)?;
    if args.output == "json" {
        println!("{}", serde_json::to_string_pretty(&envelope).unwrap_or_default());
    } else {
        print!("{}", render_doctor_table(&envelope));
    }
    Ok(())
}

fn build_envelope(args: &DoctorRequest) -> Result<Value, AppError> {
    let config_path = default_config_path()?;
    let path_str = config_path.display().to_string();
    let cli_version = env!("CARGO_PKG_VERSION");

    let run_id = format!(
        "doctor_{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    );
    let generated_at = chrono::Utc::now().to_rfc3339();

    enum LoadOutcome {
        Ok(crate::infrastructure::config_loader::CliConfig),
        Missing,
        ReadErr(String),
        ParseErr(String),
    }

    let outcome = match std::fs::read_to_string(&config_path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => LoadOutcome::Missing,
        Err(e) => LoadOutcome::ReadErr(e.to_string()),
        Ok(raw) => match load_config_from(&raw) {
            Ok(c) => LoadOutcome::Ok(c),
            Err(e) => LoadOutcome::ParseErr(e.to_string()),
        },
    };

    let (cfg_opt, config_status, errors, probe_skipped) = match &outcome {
        LoadOutcome::Ok(c) => (Some(c.clone()), "ok", vec![], false),
        LoadOutcome::Missing => (
            None,
            "missing",
            vec![json!({
                "code": "CONFIG_FILE_MISSING",
                "message": format!("未找到配置文件: {path_str}")
            })],
            true,
        ),
        LoadOutcome::ReadErr(msg) => (
            None,
            "read_error",
            vec![json!({
                "code": "CONFIG_READ_ERROR",
                "message": format!("读取配置失败: {msg}")
            })],
            true,
        ),
        LoadOutcome::ParseErr(msg) => (
            None,
            "parse_error",
            vec![json!({
                "code": "CONFIG_PARSE_ERROR",
                "message": format!("解析配置失败: {msg}")
            })],
            true,
        ),
    };

    let timeout_for_probe = match (&cfg_opt, args.timeout_ms) {
        (_, Some(ms)) => ms,
        (Some(c), None) => c.timeout_ms,
        (None, None) => 10_000u64,
    };

    let (server_url, timeout_ms_val, retry_val, probe, mut warnings, server_probe_url) =
        if let Some(ref c) = cfg_opt {
            let probe = probe_openapi_json(&c.server_url, timeout_for_probe);
            let probe_url = format!("{}/openapi.json", c.server_url.trim_end_matches('/'));
            let mut w = Vec::new();
            if !probe.reachable {
                let msg = probe
                    .error_message
                    .clone()
                    .unwrap_or_else(|| "quant 不可达".to_string());
                w.push(json!({
                    "code": "CLI_DOCTOR_SERVER_UNREACHABLE",
                    "message": msg
                }));
            }
            (
                Some(c.server_url.as_str()),
                Some(c.timeout_ms),
                Some(c.retry),
                probe,
                w,
                Some(probe_url),
            )
        } else {
            (
                None,
                None,
                None,
                OpenapiProbeOutcome {
                    reachable: false,
                    http_status: None,
                    error_message: None,
                },
                vec![],
                None,
            )
        };

    let mut status = if config_status != "ok" {
        "error"
    } else if !probe.reachable {
        "warning"
    } else {
        "ok"
    };

    let quant_val: Value = if probe.reachable {
        if let Some(ref c) = cfg_opt {
            match get_system_doctor(&c.server_url, args.sync_days, timeout_for_probe) {
                Ok(env) => {
                    if env.get("status").and_then(Value::as_str) == Some("ok") {
                        let q = env.get("data").cloned().unwrap_or(Value::Null);
                        if let Some(qo) = q.as_object() {
                            if let Some(db) = qo.get("db").and_then(Value::as_object) {
                                if !db.get("reachable").and_then(Value::as_bool).unwrap_or(false) {
                                    if status == "ok" {
                                        status = "warning";
                                    }
                                    warnings.push(json!({
                                        "code": "CLI_DOCTOR_DB_UNAVAILABLE",
                                        "message": "数据库不可达或未配置（见 data.quant.db）"
                                    }));
                                }
                            }
                            if let Some(po) = qo.get("positions").and_then(Value::as_object) {
                                if let Some(es) = po.get("error").and_then(Value::as_str) {
                                    if !es.is_empty() {
                                        if status == "ok" {
                                            status = "warning";
                                        }
                                        warnings.push(json!({
                                            "code": "CLI_DOCTOR_POSITIONS_QUERY_FAILED",
                                            "message": es
                                        }));
                                    }
                                }
                            }
                        }
                        q
                    } else {
                        if status == "ok" {
                            status = "warning";
                        }
                        warnings.push(json!({
                            "code": "CLI_DOCTOR_AGGREGATE_NON_OK",
                            "message": "服务端 /v1/system/doctor 返回非 ok"
                        }));
                        Value::Null
                    }
                }
                Err(e) => {
                    if status == "ok" {
                        status = "warning";
                    }
                    warnings.push(json!({
                        "code": "CLI_DOCTOR_AGGREGATE_FAILED",
                        "message": format!("{e}")
                    }));
                    Value::Null
                }
            }
        } else {
            Value::Null
        }
    } else {
        Value::Null
    };

    let data = json!({
        "config_path": path_str,
        "config_status": config_status,
        "probe_skipped": probe_skipped,
        "server_url": server_url,
        "timeout_ms": timeout_ms_val,
        "retry": retry_val,
        "server_probe_url": server_probe_url,
        "server_reachable": probe.reachable,
        "server_http_status": probe.http_status,
        "server_error": probe.error_message,
        "cli_version": cli_version,
        "quant": quant_val,
    });

    Ok(json!({
        "schema_version": "1.0.0",
        "command": COMMAND,
        "run_id": run_id,
        "status": status,
        "generated_at": generated_at,
        "source": "system",
        "advice_only": false,
        "decision_weight": 1,
        "data": data,
        "warnings": warnings,
        "errors": errors,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn doctor_envelope_has_command_and_data_keys() {
        let args = DoctorRequest {
            output: "json".to_string(),
            timeout_ms: None,
            sync_days: 7,
        };
        let v = build_envelope(&args).expect("envelope");
        assert_eq!(v["command"], COMMAND);
        assert!(v.get("data").is_some());
        assert!(v["data"].get("config_path").is_some());
        assert!(v["data"].get("config_status").is_some());
        assert!(v["data"].get("cli_version").is_some());
        assert!(v["data"].get("quant").is_some());
    }
}
