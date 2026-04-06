use comfy_table::presets::UTF8_FULL;
use comfy_table::{Cell, ContentArrangement, Table};
use serde_json::Value;

use crate::error::AppError;

fn truncate_middle(s: &str, head: usize, tail: usize) -> String {
    if s.len() <= head + tail + 1 {
        return s.to_string();
    }
    format!("{}...{}", &s[..head], &s[s.len() - tail..])
}

fn as_str(v: Option<&Value>) -> String {
    v.and_then(Value::as_str).unwrap_or("").to_string()
}

fn as_i64(v: Option<&Value>) -> String {
    v.and_then(Value::as_i64)
        .map(|n| n.to_string())
        .unwrap_or_else(|| "".to_string())
}

fn as_f64(v: Option<&Value>) -> String {
    v.and_then(Value::as_f64)
        .map(|n| format!("{n:.4}"))
        .unwrap_or_else(|| "".to_string())
}

fn as_bool(v: Option<&Value>) -> String {
    v.and_then(Value::as_bool)
        .map(|flag| (if flag { "是" } else { "否" }).to_string())
        .unwrap_or_else(|| "".to_string())
}

fn first_top_candidate_symbol(item: Option<&Value>) -> String {
    item.and_then(|version| version.get("top_candidates"))
        .and_then(Value::as_array)
        .and_then(|items| items.first())
        .and_then(|candidate| candidate.get("symbol"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
}

fn value_display(v: Option<&Value>) -> String {
    match v {
        Some(value) if value.is_string() => value.as_str().unwrap_or("").to_string(),
        Some(value) if value.is_number() => {
            if let Some(n) = value.as_f64() {
                if (n.fract() - 0.0).abs() < f64::EPSILON {
                    format!("{n:.0}")
                } else {
                    format!("{n:.4}")
                }
            } else {
                "".to_string()
            }
        }
        Some(value) if value.is_boolean() => as_bool(Some(value)),
        Some(value) => value.to_string(),
        None => "".to_string(),
    }
}

fn render_matrix_row(item: &Value) -> (String, String) {
    let dimension = as_str(item.get("dimension"));
    let mut details = Vec::new();

    if let Some(value) = item.get("value") {
        let rendered = value_display(Some(value));
        if !rendered.is_empty() {
            details.push(rendered);
        }
    }

    if details.is_empty() {
        for (key, value) in item.as_object().into_iter().flat_map(|obj| obj.iter()) {
            if key == "dimension" || key == "value" {
                continue;
            }
            details.push(format!("{key}={}", value_display(Some(value))));
        }
    }

    (dimension, details.join(" | "))
}

fn join_factor_names(value: Option<&Value>) -> String {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .collect::<Vec<_>>()
                .join("+")
        })
        .unwrap_or_default()
}

fn localize_scheme_name(raw: &str) -> String {
    match raw {
        "balanced" => "均衡".to_string(),
        "return_first" => "收益优先".to_string(),
        "risk_first" => "风险优先".to_string(),
        _ => raw.to_string(),
    }
}

pub fn render_sync_runs_table(payload: &Value, verbose: bool) -> String {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("end_date"),
            Cell::new("status"),
            Cell::new("timeframe"),
            Cell::new("effective_symbols_count"),
            Cell::new("run_id"),
            Cell::new("request_id"),
        ]);

    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let end_date = as_str(item.get("end_date"));
            let status = as_str(item.get("status"));
            let timeframe = as_str(item.get("timeframe"));
            let effective_symbols_count = as_i64(item.get("effective_symbols_count"));
            let run_id = truncate_middle(&as_str(item.get("run_id")), 8, 6);
            let request_id = truncate_middle(&as_str(item.get("request_id")), 8, 6);
            table.add_row(vec![
                end_date,
                status,
                timeframe,
                effective_symbols_count,
                run_id,
                request_id,
            ]);

            if verbose {
                let days = as_i64(item.get("days"));
                let selection_mode = as_str(item.get("selection_mode"));
                let written_rows = as_i64(item.get("written_rows"));
                let started_at = as_str(item.get("started_at"));
                let finished_at = as_str(item.get("finished_at"));
                let error_code = as_str(item.get("error_code"));
                let error_message = truncate_middle(&as_str(item.get("error_message")), 12, 10);
                table.add_row(vec![
                    "".to_string(),
                    format!("days={days}"),
                    format!("sel={selection_mode}"),
                    format!("written={written_rows}"),
                    format!("started={started_at}"),
                    format!("finished={finished_at} {error_code} {error_message}"),
                ]);
            }
        }
    }
    format!("Sync Runs\n{}\n", table)
}

/// 单行同步任务详情的人类可读摘要（`hf task progress`）。
pub fn render_sync_run_progress_summary(detail: &Value, verbose: bool) -> String {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("field"), Cell::new("value")]);

    let progress = detail.get("progress").unwrap_or(&Value::Null);
    let total_sym = progress
        .get("total_symbols")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let done_sym = progress
        .get("completed_symbols")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let sym_progress = if total_sym > 0 {
        format!("{done_sym}/{total_sym}")
    } else {
        format!("{done_sym}")
    };
    let total_days = progress
        .get("total_days")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let done_days = progress
        .get("completed_days")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let day_progress = if total_days > 0 {
        format!("{done_days}/{total_days}")
    } else {
        String::new()
    };

    let mut rows: Vec<(String, String)> = vec![
        ("run_id".into(), as_str(detail.get("run_id"))),
        ("status".into(), as_str(detail.get("status"))),
        ("phase".into(), as_str(detail.get("phase"))),
        ("symbols_done/total".into(), sym_progress),
        (
            "current_symbol".into(),
            as_str(progress.get("current_symbol")),
        ),
        ("selection_mode".into(), as_str(detail.get("selection_mode"))),
        ("end_date".into(), as_str(detail.get("end_date"))),
        ("timeframe".into(), as_str(detail.get("timeframe"))),
        ("days".into(), as_i64(detail.get("days"))),
        ("written_rows".into(), as_i64(detail.get("written_rows"))),
    ];
    if !day_progress.is_empty() {
        rows.push(("days_done/total".into(), day_progress));
    }
    if verbose {
        rows.push((
            "request_id".into(),
            as_str(detail.get("request_id")),
        ));
        rows.push(("started_at".into(), as_str(detail.get("started_at"))));
        rows.push(("finished_at".into(), as_str(detail.get("finished_at"))));
        rows.push(("error_code".into(), as_str(detail.get("error_code"))));
        rows.push((
            "error_message".into(),
            truncate_middle(&as_str(detail.get("error_message")), 24, 16),
        ));
        rows.push((
            "cancel_requested_at".into(),
            as_str(detail.get("cancel_requested_at")),
        ));
    }
    for (k, v) in rows {
        table.add_row(vec![Cell::new(k), Cell::new(v)]);
    }

    format!("Sync run progress\n{}\n", table)
}

pub fn render_market_data_bars_table(payload: &Value, verbose: bool) -> String {
    let mut table = Table::new();
    let show_name = payload
        .get("items")
        .and_then(Value::as_array)
        .is_some_and(|items| {
            items
                .iter()
                .any(|item| item.get("symbol_name_zh").is_some())
        });
    let mut header = vec![
        Cell::new("bar_time"),
        Cell::new("symbol"),
    ];
    if show_name {
        header.push(Cell::new("名称"));
    }
    header.extend([
        Cell::new("timeframe"),
        Cell::new("close"),
    ]);
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(header);

    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let bar_time = as_str(item.get("bar_time"));
            let symbol = as_str(item.get("symbol"));
            let name_zh = item
                .get("symbol_name_zh")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let timeframe = as_str(item.get("timeframe"));
            let close = as_f64(item.get("close"));
            let mut row = vec![bar_time, symbol];
            if show_name {
                row.push(name_zh);
            }
            row.extend([timeframe, close]);
            table.add_row(row);

            if verbose {
                let open = as_f64(item.get("open"));
                let high = as_f64(item.get("high"));
                let low = as_f64(item.get("low"));
                let volume = as_f64(item.get("volume"));
                let source = as_str(item.get("data_source"));
                let mut detail_row = vec![
                    "".to_string(),
                    format!("o/h/l={open}/{high}/{low}"),
                ];
                if show_name {
                    detail_row.push(String::new());
                }
                detail_row.extend([
                    format!("vol={volume}"),
                    format!("src={source}"),
                ]);
                table.add_row(detail_row);
            }
        }
    }
    format!("Market Data\n{}\n", table)
}

pub fn render_pipeline_daily_table(payload: &Value) -> String {
    let mut summary = Table::new();
    summary
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("交易日"),
            Cell::new("状态"),
            Cell::new("评分版本"),
            Cell::new("样本数"),
            Cell::new("因子覆盖率"),
        ]);

    let as_of = as_str(payload.get("data").and_then(|d| d.get("as_of")));
    let status = as_str(payload.get("status"));
    let score_version = as_str(
        payload
            .get("data")
            .and_then(|d| d.get("l2_decision"))
            .and_then(|x| x.get("score_version")),
    );
    let universe_size = as_i64(
        payload
            .get("data")
            .and_then(|d| d.get("l2_decision"))
            .and_then(|x| x.get("universe_size")),
    );
    let factor_coverage = as_f64(
        payload
            .get("data")
            .and_then(|d| d.get("factor_snapshot"))
            .and_then(|x| x.get("coverage_rate")),
    );
    summary.add_row(vec![
        as_of,
        status,
        score_version,
        universe_size,
        factor_coverage,
    ]);

    let mut top = Table::new();
    top.load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("排名"),
            Cell::new("标的"),
            Cell::new("得分"),
        ]);
    if let Some(items) = payload
        .get("data")
        .and_then(|d| d.get("l2_decision"))
        .and_then(|x| x.get("top_candidates"))
        .and_then(Value::as_array)
    {
        for item in items {
            top.add_row(vec![
                as_i64(item.get("rank")),
                as_str(item.get("symbol")),
                as_f64(item.get("score")),
            ]);
        }
    }

    let mut availability = Table::new();
    availability
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("因子名"),
            Cell::new("有效数"),
            Cell::new("缺失数"),
            Cell::new("可用率"),
        ]);
    if let Some(items) = payload
        .get("data")
        .and_then(|d| d.get("l2_decision"))
        .and_then(|x| x.get("factor_availability"))
        .and_then(Value::as_array)
    {
        for item in items {
            availability.add_row(vec![
                as_str(item.get("factor_name")),
                as_i64(item.get("present_count")),
                as_i64(item.get("missing_count")),
                as_f64(item.get("availability_rate")),
            ]);
        }
    }

    let mut ma_cross = Table::new();
    ma_cross
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("标的"),
            Cell::new("金叉"),
            Cell::new("死叉"),
            Cell::new("SMA5"),
            Cell::new("SMA10"),
            Cell::new("可用"),
        ]);
    if let Some(by) = payload
        .get("data")
        .and_then(|d| d.get("technical"))
        .and_then(|t| t.get("ma5_ma10"))
        .and_then(|m| m.get("by_symbol"))
        .and_then(Value::as_object)
    {
        let mut keys: Vec<&String> = by.keys().collect();
        keys.sort();
        for sym in keys {
            if let Some(v) = by.get(sym) {
                ma_cross.add_row(vec![
                    sym.clone(),
                    json_bool_label(v.get("golden_cross")),
                    json_bool_label(v.get("death_cross")),
                    as_f64(v.get("sma5")),
                    as_f64(v.get("sma10")),
                    json_bool_label(v.get("available")),
                ]);
            }
        }
    }

    format!(
        "日频管线摘要\n{}\n候选标的（最多5）\n{}\n因子可用性\n{}\nMA5/MA10\n{}\n",
        summary, top, availability, ma_cross
    )
}

pub fn render_pipeline_compare_table(payload: &Value) -> String {
    let mut summary = Table::new();
    summary
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("指标"), Cell::new("值")]);

    let data = payload.get("data");
    let start_date = as_str(data.and_then(|d| d.get("start_date")));
    let end_date = as_str(data.and_then(|d| d.get("end_date")));
    let days = as_i64(
        data.and_then(|d| d.get("summary"))
            .and_then(|s| s.get("days")),
    );
    let avg_warning_count_v1 = as_f64(
        data.and_then(|d| d.get("summary"))
            .and_then(|s| s.get("avg_warning_count_v1")),
    );
    let avg_warning_count_v1_1 = as_f64(
        data.and_then(|d| d.get("summary"))
            .and_then(|s| s.get("avg_warning_count_v1_1")),
    );
    let avg_min_availability_v1 = as_f64(
        data.and_then(|d| d.get("summary"))
            .and_then(|s| s.get("avg_min_availability_v1")),
    );
    let avg_min_availability_v1_1 = as_f64(
        data.and_then(|d| d.get("summary"))
            .and_then(|s| s.get("avg_min_availability_v1_1")),
    );
    let top1_symbol_change_days = as_i64(
        data.and_then(|d| d.get("summary"))
            .and_then(|s| s.get("top1_symbol_change_days")),
    );

    summary.add_row(vec!["开始日期".to_string(), start_date]);
    summary.add_row(vec!["结束日期".to_string(), end_date]);
    summary.add_row(vec!["天数".to_string(), days]);
    summary.add_row(vec!["v1平均告警数".to_string(), avg_warning_count_v1]);
    summary.add_row(vec!["v1.1平均告警数".to_string(), avg_warning_count_v1_1]);
    summary.add_row(vec![
        "v1平均最小可用率".to_string(),
        avg_min_availability_v1,
    ]);
    summary.add_row(vec![
        "v1.1平均最小可用率".to_string(),
        avg_min_availability_v1_1,
    ]);
    summary.add_row(vec!["Top1变更天数".to_string(), top1_symbol_change_days]);

    let mut daily = Table::new();
    daily
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("日期"),
            Cell::new("v1_top1"),
            Cell::new("v1.1_top1"),
            Cell::new("v1_warn"),
            Cell::new("v1.1_warn"),
            Cell::new("v1_min_avail"),
            Cell::new("v1.1_min_avail"),
        ]);

    if let Some(items) = data
        .and_then(|d| d.get("daily_items"))
        .and_then(Value::as_array)
    {
        for item in items {
            let v1 = item.get("v1");
            let v1_1 = item.get("v1_1");
            let v1_warn = as_i64(v1.and_then(|x| x.get("warning_count")));
            let v1_1_warn = as_i64(v1_1.and_then(|x| x.get("warning_count")));
            let v1_min_avail = as_f64(v1.and_then(|x| x.get("min_availability")));
            let v1_1_min_avail = as_f64(v1_1.and_then(|x| x.get("min_availability")));

            daily.add_row(vec![
                as_str(item.get("as_of")),
                first_top_candidate_symbol(v1),
                first_top_candidate_symbol(v1_1),
                v1_warn,
                v1_1_warn,
                v1_min_avail,
                v1_1_min_avail,
            ]);
        }
    }

    let mut out = format!("版本对比回放\n版本对比汇总\n{}\n逐日明细\n{}\n", summary, daily);

    if let Some(analytics) = data.and_then(|d| d.get("analytics")) {
        if let Some(return_metrics) = analytics.get("return_metrics") {
            let mut metrics = Table::new();
            metrics
                .load_preset(UTF8_FULL)
                .set_content_arrangement(ContentArrangement::Dynamic)
                .set_header(vec![
                    Cell::new("指标"),
                    Cell::new("v1"),
                    Cell::new("v1.1"),
                    Cell::new("diff"),
                ]);

            metrics.add_row(vec![
                "累计收益".to_string(),
                as_f64(return_metrics.get("v1").and_then(|v| v.get("cumulative_return"))),
                as_f64(return_metrics.get("v1_1").and_then(|v| v.get("cumulative_return"))),
                as_f64(
                    return_metrics
                        .get("diff")
                        .and_then(|v| v.get("excess_cumulative_return_v1_1_vs_v1")),
                ),
            ]);
            metrics.add_row(vec![
                "胜率".to_string(),
                as_f64(return_metrics.get("v1").and_then(|v| v.get("win_rate"))),
                as_f64(return_metrics.get("v1_1").and_then(|v| v.get("win_rate"))),
                "".to_string(),
            ]);
            metrics.add_row(vec![
                "最大回撤".to_string(),
                as_f64(return_metrics.get("v1").and_then(|v| v.get("max_drawdown"))),
                as_f64(return_metrics.get("v1_1").and_then(|v| v.get("max_drawdown"))),
                "".to_string(),
            ]);
            metrics.add_row(vec![
                "年化波动".to_string(),
                as_f64(
                    return_metrics
                        .get("v1")
                        .and_then(|v| v.get("annualized_volatility")),
                ),
                as_f64(
                    return_metrics
                        .get("v1_1")
                        .and_then(|v| v.get("annualized_volatility")),
                ),
                "".to_string(),
            ]);
            metrics.add_row(vec![
                "夏普".to_string(),
                as_f64(return_metrics.get("v1").and_then(|v| v.get("sharpe"))),
                as_f64(return_metrics.get("v1_1").and_then(|v| v.get("sharpe"))),
                as_f64(
                    return_metrics
                        .get("diff")
                        .and_then(|v| v.get("excess_sharpe_v1_1_vs_v1")),
                ),
            ]);

            out.push_str(&format!("收益与风险统计\n{}\n", metrics));
        }

        if let Some(items) = analytics
            .get("group_stability")
            .and_then(|g| g.get("items"))
            .and_then(Value::as_array)
        {
            let mut groups = Table::new();
            groups
                .load_preset(UTF8_FULL)
                .set_content_arrangement(ContentArrangement::Dynamic)
                .set_header(vec![
                    Cell::new("industry"),
                    Cell::new("cap_bucket"),
                    Cell::new("sample_days"),
                    Cell::new("v1_cum"),
                    Cell::new("v1.1_cum"),
                    Cell::new("diff_cum"),
                    Cell::new("flag"),
                ]);

            for item in items {
                groups.add_row(vec![
                    as_str(item.get("industry")),
                    as_str(item.get("market_cap_bucket")),
                    as_i64(item.get("sample_days")),
                    as_f64(item.get("v1").and_then(|v| v.get("cumulative_return"))),
                    as_f64(item.get("v1_1").and_then(|v| v.get("cumulative_return"))),
                    as_f64(item.get("diff").and_then(|v| v.get("excess_cumulative_return"))),
                    as_str(item.get("stability_flag")),
                ]);
            }

            out.push_str(&format!(
                "分组稳定性（industry + market_cap_bucket）\n{}\n",
                groups
            ));
        }
    }

    out
}

pub fn render_factor_optimize_table(payload: &Value) -> Result<String, AppError> {
    let mut summary = Table::new();
    summary
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("指标"), Cell::new("值")]);

    let recommended = localize_scheme_name(&as_str(
        payload
            .get("data")
            .and_then(|d| d.get("recommended_scheme")),
    ));
    let start_date = as_str(
        payload
            .get("audit")
            .and_then(|a| a.get("analysis_period"))
            .and_then(|p| p.get("start_date")),
    );
    let end_date = as_str(
        payload
            .get("audit")
            .and_then(|a| a.get("analysis_period"))
            .and_then(|p| p.get("end_date")),
    );
    let correlation_threshold = as_f64(
        payload
            .get("data")
            .and_then(|d| d.get("correlation_analysis"))
            .and_then(|a| a.get("threshold")),
    );
    let alert_count = as_i64(
        payload
            .get("data")
            .and_then(|d| d.get("correlation_analysis"))
            .and_then(|a| a.get("alert_count")),
    );

    summary.add_row(vec!["开始日期".to_string(), start_date]);
    summary.add_row(vec!["结束日期".to_string(), end_date]);
    summary.add_row(vec!["推荐方案".to_string(), recommended]);
    if !correlation_threshold.is_empty() {
        summary.add_row(vec!["相关性阈值".to_string(), correlation_threshold]);
    }
    if !alert_count.is_empty() {
        summary.add_row(vec!["相关性告警数".to_string(), alert_count]);
    }

    let mut alerts = Table::new();
    alerts
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("factor_a"),
            Cell::new("factor_b"),
            Cell::new("correlation"),
            Cell::new("severity"),
            Cell::new("suggestion"),
        ]);

    if let Some(items) = payload
        .get("data")
        .and_then(|d| d.get("correlation_analysis"))
        .and_then(|a| a.get("alerts"))
        .and_then(Value::as_array)
    {
        for item in items {
            alerts.add_row(vec![
                as_str(item.get("factor_a")),
                as_str(item.get("factor_b")),
                as_f64(item.get("correlation")),
                as_str(item.get("severity")),
                as_str(item.get("suggestion")),
            ]);
        }
    }

    let report = payload.get("data").and_then(|d| d.get("report"));
    let mut report_summary = Table::new();
    report_summary
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("指标"), Cell::new("值")]);
    report_summary.add_row(vec![
        "推荐方案".to_string(),
        localize_scheme_name(&as_str(
            report
                .and_then(|r| r.get("summary"))
                .and_then(|s| s.get("recommended_scheme")),
        )),
    ]);
    report_summary.add_row(vec![
        "关键结论".to_string(),
        report
            .and_then(|r| r.get("summary"))
            .and_then(|s| s.get("key_findings"))
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .map(|item| value_display(Some(item)))
                    .collect::<Vec<_>>()
                    .join("；")
            })
            .unwrap_or_else(|| "".to_string()),
    ]);

    let mut matrix = Table::new();
    matrix
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("维度"), Cell::new("值")]);
    if let Some(items) = report
        .and_then(|r| r.get("matrix_10d"))
        .and_then(Value::as_array)
    {
        for item in items {
            let (dimension, value) = render_matrix_row(item);
            matrix.add_row(vec![dimension, value]);
        }
    }

    let mut checklist = Table::new();
    checklist
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("检查项"), Cell::new("完成")]);
    if let Some(items) = report
        .and_then(|r| r.get("g3_checklist"))
        .and_then(Value::as_array)
    {
        for item in items {
            checklist.add_row(vec![
                as_str(item.get("item")),
                as_bool(item.get("checked")),
            ]);
        }
    }

    let mut schemes = Table::new();
    schemes
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("方案"),
            Cell::new("预期Sharpe"),
            Cell::new("预期回撤"),
            Cell::new("权重"),
        ]);

    let items = payload
        .get("data")
        .and_then(|d| d.get("recommendations"))
        .and_then(Value::as_array)
        .ok_or_else(|| AppError::InvalidArgs("missing data.recommendations".to_string()))?;

    for item in items {
        let name = localize_scheme_name(&as_str(item.get("name")));
        let expected_sharpe = as_f64(item.get("expected_sharpe"));
        let expected_drawdown = as_f64(item.get("expected_drawdown"));
        let weights = item
            .get("weights")
            .and_then(Value::as_object)
            .map(|m| {
                m.iter()
                    .map(|(k, v)| format!("{k}={}", v.as_f64().unwrap_or(0.0)))
                    .collect::<Vec<_>>()
                    .join(",")
        })
            .unwrap_or_else(|| "".to_string());
        schemes.add_row(vec![name, expected_sharpe, expected_drawdown, weights]);
    }

    let top_combinations = payload
        .get("data")
        .and_then(|d| d.get("top_combinations"));

    let mut combo_summary = Table::new();
    combo_summary
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("指标"), Cell::new("值")]);
    combo_summary.add_row(vec![
        "ranking_profile".to_string(),
        as_str(top_combinations.and_then(|x| x.get("ranking_profile"))),
    ]);
    combo_summary.add_row(vec![
        "factor_pool_size".to_string(),
        as_i64(
            top_combinations
                .and_then(|x| x.get("search_space"))
                .and_then(|s| s.get("factor_pool_size")),
        ),
    ]);
    combo_summary.add_row(vec![
        "combination_range".to_string(),
        format!(
            "{}~{}",
            as_i64(
                top_combinations
                    .and_then(|x| x.get("search_space"))
                    .and_then(|s| s.get("combination_size_min")),
            ),
            as_i64(
                top_combinations
                    .and_then(|x| x.get("search_space"))
                    .and_then(|s| s.get("combination_size_max")),
            )
        ),
    ]);
    combo_summary.add_row(vec![
        "candidate_count".to_string(),
        as_i64(
            top_combinations
                .and_then(|x| x.get("search_space"))
                .and_then(|s| s.get("candidate_count")),
        ),
    ]);

    let mut combo_items = Table::new();
    combo_items
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("rank"),
            Cell::new("factors"),
            Cell::new("composite_score"),
            Cell::new("return_score"),
            Cell::new("risk_score"),
            Cell::new("penalty"),
            Cell::new("alerts"),
        ]);
    if let Some(items) = top_combinations
        .and_then(|x| x.get("items"))
        .and_then(Value::as_array)
    {
        for item in items {
            let factors = item
                .get("factors")
                .and_then(Value::as_array)
                .map(|factors| {
                    factors
                        .iter()
                        .map(|x| x.as_str().unwrap_or_default().to_string())
                        .collect::<Vec<_>>()
                        .join("+")
                })
                .unwrap_or_else(String::new);

            combo_items.add_row(vec![
                as_i64(item.get("rank")),
                factors,
                as_f64(item.get("composite_score")),
                as_f64(item.get("return_score")),
                as_f64(item.get("risk_score")),
                as_f64(item.get("redundancy_penalty")),
                as_i64(item.get("alerts_inside")),
            ]);
        }
    }

    Ok(format!(
        "因子优化建议\n{}\n相关性告警\n{}\n10维评估摘要\n{}\n{}\nG3 checklist\n{}\nTop5 组合推荐\n组合空间\n{}\n{}\n方案明细\n{}\n",
        summary, alerts, report_summary, matrix, checklist, combo_summary, combo_items, schemes
    ))
}

pub fn render_factor_replay_table(payload: &Value) -> String {
    let mut summary = Table::new();
    summary
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("指标"), Cell::new("值")]);

    let summary_data = payload.get("summary");
    summary.add_row(vec![
        "days".to_string(),
        as_i64(summary_data.and_then(|value| value.get("days"))),
    ]);
    summary.add_row(vec![
        "error_days".to_string(),
        as_i64(summary_data.and_then(|value| value.get("error_days"))),
    ]);
    summary.add_row(vec![
        "pass_days".to_string(),
        as_i64(summary_data.and_then(|value| value.get("pass_days"))),
    ]);
    summary.add_row(vec![
        "watch_days".to_string(),
        as_i64(summary_data.and_then(|value| value.get("watch_days"))),
    ]);
    summary.add_row(vec![
        "fail_days".to_string(),
        as_i64(summary_data.and_then(|value| value.get("fail_days"))),
    ]);
    summary.add_row(vec![
        "avg_alert_count".to_string(),
        as_f64(summary_data.and_then(|value| value.get("avg_alert_count"))),
    ]);
    summary.add_row(vec![
        "top1_change_days".to_string(),
        as_i64(summary_data.and_then(|value| value.get("top1_change_days"))),
    ]);

    let mut daily = Table::new();
    daily
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("as_of"),
            Cell::new("fetch_status"),
            Cell::new("release_gate_status"),
            Cell::new("alert_count"),
            Cell::new("top1_factors"),
        ]);

    if let Some(items) = payload.get("daily_items").and_then(Value::as_array) {
        for item in items {
            daily.add_row(vec![
                as_str(item.get("as_of")),
                as_str(item.get("fetch_status")),
                as_str(item.get("release_gate_status")),
                as_i64(item.get("alert_count")),
                join_factor_names(item.get("top1_factors")),
            ]);
        }
    }

    format!("因子回放汇总\n{}\n逐日回放明细\n{}\n", summary, daily)
}

pub fn render_signal_snapshot_table(payload: &Value) -> String {
    let data = payload.get("data");
    let sm = data.and_then(|d| d.get("signal_matrix"));
    let signal_version = as_str(sm.and_then(|d| d.get("signal_version")));
    let coverage = as_f64(sm.and_then(|d| d.get("coverage_rate")));

    let mut header = Table::new();
    header
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![Cell::new("信号版本"), Cell::new("覆盖率")]);
    header.add_row(vec![signal_version, coverage]);

    let mut rows_table = Table::new();
    rows_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("标的"),
            Cell::new("因子"),
            Cell::new("原始值"),
            Cell::new("信号值"),
            Cell::new("方向"),
        ]);

    if let Some(items) = sm.and_then(|d| d.get("rows")).and_then(Value::as_array) {
        for item in items {
            rows_table.add_row(vec![
                as_str(item.get("symbol")),
                as_str(item.get("factor_name")),
                as_f64(item.get("raw_value")),
                as_f64(item.get("signal_value")),
                as_i64(item.get("direction")),
            ]);
        }
    }

    let mut composite = Table::new();
    composite
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("标的"),
            Cell::new("综合分"),
            Cell::new("参与因子数"),
        ]);

    if let Some(items) = sm.and_then(|d| d.get("composite_scores")).and_then(Value::as_array) {
        for item in items {
            composite.add_row(vec![
                as_str(item.get("symbol")),
                as_f64(item.get("composite_score")),
                as_i64(item.get("factor_count")),
            ]);
        }
    }

    let mut ma_cross = Table::new();
    ma_cross
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("标的"),
            Cell::new("金叉"),
            Cell::new("死叉"),
            Cell::new("SMA5"),
            Cell::new("SMA10"),
            Cell::new("可用"),
        ]);
    if let Some(by) = data
        .and_then(|d| d.get("technical"))
        .and_then(|t| t.get("ma5_ma10"))
        .and_then(|m| m.get("by_symbol"))
        .and_then(Value::as_object)
    {
        let mut keys: Vec<&String> = by.keys().collect();
        keys.sort();
        for sym in keys {
            if let Some(v) = by.get(sym) {
                ma_cross.add_row(vec![
                    sym.clone(),
                    json_bool_label(v.get("golden_cross")),
                    json_bool_label(v.get("death_cross")),
                    as_f64(v.get("sma5")),
                    as_f64(v.get("sma10")),
                    json_bool_label(v.get("available")),
                ]);
            }
        }
    }

    format!(
        "L3 信号快照\n{}\n信号明细\n{}\n综合分排名\n{}\nMA5/MA10\n{}\n",
        header, rows_table, composite, ma_cross
    )
}

fn json_bool_label(v: Option<&Value>) -> String {
    match v.and_then(Value::as_bool) {
        Some(true) => "是".to_string(),
        Some(false) => "否".to_string(),
        None => "—".to_string(),
    }
}

fn ic_rating(ic_ir: f64) -> &'static str {
    if ic_ir >= 0.5 {
        "良好"
    } else if ic_ir >= 0.2 {
        "中等"
    } else {
        "偏弱"
    }
}

pub fn render_signal_evaluate_table(payload: &Value) -> String {
    let data = payload.get("data");
    let start = as_str(data.and_then(|d| d.get("start_date")));
    let end = as_str(data.and_then(|d| d.get("end_date")));
    let fwd = as_i64(data.and_then(|d| d.get("forward_days")));
    let days = as_i64(data.and_then(|d| d.get("trading_days_evaluated")));

    let mut header = Table::new();
    header
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("区间"),
            Cell::new("前瞻"),
            Cell::new("评估天数"),
        ]);
    header.add_row(vec![
        format!("{start} → {end}"),
        format!("T+{fwd}"),
        days,
    ]);

    let mut ic_table = Table::new();
    ic_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("因子"),
            Cell::new("均值IC"),
            Cell::new("IC_IR"),
            Cell::new("命中率"),
            Cell::new("评级"),
        ]);

    if let Some(ic_report) = data.and_then(|d| d.get("ic_report")) {
        if let Some(factors) = ic_report.get("per_factor").and_then(Value::as_array) {
            for f in factors {
                let ir_val = f.get("ic_ir").and_then(Value::as_f64).unwrap_or(0.0);
                ic_table.add_row(vec![
                    as_str(f.get("factor_name")),
                    as_f64(f.get("mean_ic")),
                    as_f64(f.get("ic_ir")),
                    format!(
                        "{:.1}%",
                        f.get("hit_rate").and_then(Value::as_f64).unwrap_or(0.0) * 100.0
                    ),
                    ic_rating(ir_val).to_string(),
                ]);
            }
        }
        if let Some(comp) = ic_report.get("composite") {
            let ir_val = comp.get("ic_ir").and_then(Value::as_f64).unwrap_or(0.0);
            ic_table.add_row(vec![
                "★ 综合信号".to_string(),
                as_f64(comp.get("mean_ic")),
                as_f64(comp.get("ic_ir")),
                format!(
                    "{:.1}%",
                    comp.get("hit_rate").and_then(Value::as_f64).unwrap_or(0.0) * 100.0
                ),
                ic_rating(ir_val).to_string(),
            ]);
        }
    }

    let mut drift_table = Table::new();
    drift_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("指标"),
            Cell::new("漂移Z"),
            Cell::new("状态"),
        ]);

    if let Some(drift) = data.and_then(|d| d.get("drift_diagnostics")) {
        if let Some(factors) = drift.get("factor_drift").and_then(Value::as_array) {
            for f in factors {
                let flag = f.get("drift_flag").and_then(Value::as_bool).unwrap_or(false);
                drift_table.add_row(vec![
                    as_str(f.get("factor_name")),
                    as_f64(f.get("drift_z")),
                    if flag { "⚠ 漂移" } else { "✓ 正常" }.to_string(),
                ]);
            }
        }
        if let Some(cov) = drift.get("coverage_drift") {
            let flag = cov.get("drift_flag").and_then(Value::as_bool).unwrap_or(false);
            drift_table.add_row(vec![
                "覆盖率".to_string(),
                as_f64(cov.get("drift_z")),
                if flag { "⚠ 漂移" } else { "✓ 正常" }.to_string(),
            ]);
        }
        if let Some(rt) = drift.get("rank_turnover") {
            let stable = rt.get("stable").and_then(Value::as_bool).unwrap_or(true);
            drift_table.add_row(vec![
                "排名周转率".to_string(),
                as_f64(rt.get("mean_turnover")),
                if stable { "✓ 稳定" } else { "⚠ 不稳定" }.to_string(),
            ]);
        }
    }

    format!(
        "L3 信号评估\n{}\nIC 报告\n{}\n漂移诊断\n{}\n",
        header, ic_table, drift_table
    )
}

pub fn render_portfolio_optimize_table(payload: &Value) -> String {
    let data = payload.get("data");
    let as_of = as_str(data.and_then(|d| d.get("as_of")));
    let opt_status = as_str(data.and_then(|d| d.get("optimization_status")));
    let fallback_reason = as_str(data.and_then(|d| d.get("fallback_reason")));

    let report = data.and_then(|d| d.get("optimization_report"));
    let solver = as_str(report.and_then(|r| r.get("solver")));
    let solve_ms = as_i64(report.and_then(|r| r.get("solve_time_ms")));
    let obj_val = as_f64(report.and_then(|r| r.get("objective_value")));
    let risk_contrib = as_f64(report.and_then(|r| r.get("risk_contribution")));
    let turnover_cost = as_f64(report.and_then(|r| r.get("turnover_cost")));

    let mut header = Table::new();
    header
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("日期"),
            Cell::new("求解状态"),
            Cell::new("求解器"),
            Cell::new("耗时(ms)"),
            Cell::new("目标值"),
            Cell::new("风险贡献"),
            Cell::new("换手成本"),
        ]);
    header.add_row(vec![
        as_of.clone(),
        opt_status.clone(),
        solver,
        solve_ms,
        obj_val,
        risk_contrib,
        turnover_cost,
    ]);

    let mut weights_table = Table::new();
    weights_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("标的"),
            Cell::new("目标权重"),
            Cell::new("上期权重"),
            Cell::new("变动"),
        ]);

    if let Some(rows) = data
        .and_then(|d| d.get("target_weights"))
        .and_then(Value::as_array)
    {
        for row in rows {
            let w = row.get("weight").and_then(Value::as_f64).unwrap_or(0.0);
            let pw = row.get("prev_weight").and_then(Value::as_f64).unwrap_or(0.0);
            let delta = row.get("delta").and_then(Value::as_f64).unwrap_or(0.0);
            let delta_str = if delta >= 0.0 {
                format!("+{:.2}%", delta * 100.0)
            } else {
                format!("{:.2}%", delta * 100.0)
            };
            weights_table.add_row(vec![
                as_str(row.get("symbol")),
                format!("{:.2}%", w * 100.0),
                format!("{:.2}%", pw * 100.0),
                delta_str,
            ]);
        }
    }

    let fallback_note = if !fallback_reason.is_empty() {
        format!("\n[降级原因: {fallback_reason}]")
    } else {
        String::new()
    };

    format!(
        "组合优化结果（{as_of}）  求解状态: {opt_status}\n{}\n目标权重\n{}{}\n",
        header, weights_table, fallback_note
    )
}

pub fn render_risk_check_table(payload: &Value) -> String {
    let data = payload.get("data");
    let as_of = as_str(data.and_then(|d| d.get("as_of")));
    let risk_gate = as_str(data.and_then(|d| d.get("risk_gate")));
    let regime = as_str(data.and_then(|d| d.get("regime")));
    let regime_vol = data
        .and_then(|d| d.get("regime_vol"))
        .and_then(Value::as_f64)
        .map(|v| format!("{:.1}%", v * 100.0))
        .unwrap_or_else(|| "n/a".to_string());

    let mut checks_table = Table::new();
    checks_table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("检查项"),
            Cell::new("实际值"),
            Cell::new("阈值"),
            Cell::new("状态"),
        ]);

    if let Some(checks) = data
        .and_then(|d| d.get("checks"))
        .and_then(Value::as_array)
    {
        for check in checks {
            let name = as_str(check.get("name"));
            let value = check.get("value").and_then(Value::as_f64).unwrap_or(0.0);
            let threshold = check.get("threshold").and_then(Value::as_f64).unwrap_or(0.0);
            let passed = check.get("passed").and_then(Value::as_bool).unwrap_or(false);
            let status_str = if passed { "✓" } else { "✗ BLOCK" };
            checks_table.add_row(vec![
                name,
                format!("{:.1}%", value * 100.0),
                format!("{:.1}%", threshold * 100.0),
                status_str.to_string(),
            ]);
        }
    }

    let gate_line = if risk_gate == "pass" {
        "风险门控: PASS ✓".to_string()
    } else {
        let block_codes = data
            .and_then(|d| d.get("block_codes"))
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join(", ")
            })
            .unwrap_or_default();
        format!("风险门控: BLOCK ✗  [{block_codes}]")
    };

    format!(
        "风险门控检查（{as_of}）  市场状态: {regime}（波动率={regime_vol}）\n{}\n{}\n",
        checks_table, gate_line
    )
}

fn fmt_dollar_compact(v: f64) -> String {
    if v >= 1_000_000.0 {
        format!("{:.0}M", v / 1_000_000.0)
    } else if v >= 10_000.0 {
        format!("{:.0}K", v / 1_000.0)
    } else {
        format!("{:.0}", v)
    }
}

pub fn render_pretrade_check_table(payload: &Value) -> String {
    let data = payload.get("data");
    let as_of = as_str(data.and_then(|d| d.get("as_of")));
    let ot = data
        .and_then(|d| d.get("overall_tradable"))
        .and_then(Value::as_bool)
        .map(|b| if b { "YES" } else { "NO" })
        .unwrap_or("n/a");
    let tip = data
        .and_then(|d| d.get("total_impact_bp"))
        .and_then(Value::as_f64)
        .map(|x| format!("{:.1}bp", x))
        .unwrap_or_else(|| "n/a".to_string());

    let mut out = format!("as_of: {as_of}   overall_tradable: {ot}   total_impact: {tip}\n\nOrders\n");

    if let Some(orders) = data.and_then(|d| d.get("orders")).and_then(Value::as_array) {
        for row in orders {
            let sym = as_str(row.get("symbol"));
            let w = row
                .get("target_weight")
                .and_then(Value::as_f64)
                .map(|x| format!("{:.0}%", x * 100.0))
                .unwrap_or_else(|| "n/a".to_string());
            let tn = row
                .get("target_notional")
                .and_then(Value::as_f64)
                .map(|x| format!("{:.0}", x))
                .unwrap_or_else(|| "n/a".to_string());
            let adv = row
                .get("adv")
                .and_then(Value::as_f64)
                .map(fmt_dollar_compact)
                .unwrap_or_else(|| "n/a".to_string());
            let part = row
                .get("participation_rate")
                .and_then(Value::as_f64)
                .map(|x| format!("{:.2}%", x * 100.0))
                .unwrap_or_else(|| "n/a".to_string());
            let sig = row
                .get("sigma")
                .and_then(Value::as_f64)
                .map(|x| format!("{:.0}%", x * 100.0))
                .unwrap_or_else(|| "n/a".to_string());
            let imp = row
                .get("impact_bp")
                .and_then(Value::as_f64)
                .map(|x| format!("{:.1}bp", x))
                .unwrap_or_else(|| "n/a".to_string());
            let ok = row
                .get("tradable")
                .and_then(Value::as_bool)
                .map(|b| if b { "✓" } else { "✗" })
                .unwrap_or("?");
            out.push_str(&format!(
                "  {sym}   w={w}   notional={tn}   ADV={adv}   part={part}   σ={sig}   impact={imp}   {ok}\n"
            ));
        }
    }

    out
}

pub fn render_monitor_health_report_table(payload: &Value) -> String {
    let data = payload.get("data");
    let as_of = as_str(data.and_then(|d| d.get("as_of")));
    if data.and_then(|d| d.get("skipped")).and_then(Value::as_bool) == Some(true) {
        let reason = as_str(data.and_then(|d| d.get("skip_reason")));
        return format!("as_of: {as_of}   skipped (非交易日)\n  reason: {reason}\n");
    }

    let overall = data
        .and_then(|d| d.get("overall_rating"))
        .and_then(Value::as_str)
        .unwrap_or("n/a")
        .to_uppercase();

    let mut out = format!("as_of: {as_of}   overall: {overall}\n\nFactor Health\n");

    if let Some(fh) = data.and_then(|d| d.get("factor_health")).and_then(Value::as_object) {
        let total = fh.get("total").and_then(Value::as_u64).unwrap_or(0);
        let ok_c = fh.get("ok_count").and_then(Value::as_u64).unwrap_or(0);
        let warn_c = fh.get("warn_count").and_then(Value::as_u64).unwrap_or(0);
        let miss_c = fh.get("miss_count").and_then(Value::as_u64).unwrap_or(0);
        out.push_str(&format!(
            "  total={total}  ok={ok_c}  warn={warn_c}  miss={miss_c}\n"
        ));
        if let Some(details) = fh.get("details").and_then(Value::as_array) {
            for row in details {
                let st = as_str(row.get("status"));
                if st != "warn" && st != "miss" {
                    continue;
                }
                let name = as_str(row.get("factor_name"));
                let pct = row
                    .get("availability_rate")
                    .and_then(Value::as_f64)
                    .map(|r| format!("{:.0}%", r * 100.0))
                    .unwrap_or_else(|| "n/a".to_string());
                out.push_str(&format!("  {}  {}  {}\n", st.to_uppercase(), name, pct));
            }
        }
    } else {
        out.push_str("  (n/a)\n");
    }

    out.push_str("\nSignal Health\n");
    if let Some(sh) = data.and_then(|d| d.get("signal_health")).and_then(Value::as_object) {
        let cov = sh
            .get("coverage_rate")
            .and_then(Value::as_f64)
            .map(|r| format!("{:.0}%", r * 100.0))
            .unwrap_or_else(|| "n/a".to_string());
        let mean = sh
            .get("composite_score_mean")
            .and_then(Value::as_f64)
            .map(|v| format!("{:.2}", v))
            .unwrap_or_else(|| "n/a".to_string());
        let std = sh
            .get("composite_score_std")
            .and_then(Value::as_f64)
            .map(|v| format!("{:.2}", v))
            .unwrap_or_else(|| "n/a".to_string());
        out.push_str(&format!(
            "  coverage={cov}  mean={mean}  std={std}\n"
        ));
    } else {
        out.push_str("  (n/a)\n");
    }

    out.push_str("\nRisk\n");
    if let Some(rh) = data.and_then(|d| d.get("risk_health")).and_then(Value::as_object) {
        let regime = as_str(rh.get("regime"));
        let n_trig = rh
            .get("triggered_rules")
            .and_then(Value::as_array)
            .map(|a| a.len())
            .unwrap_or(0);
        out.push_str(&format!("  regime={regime}  triggered={n_trig}\n"));
    } else {
        out.push_str("  (n/a)\n");
    }

    out.push('\n');
    out
}
