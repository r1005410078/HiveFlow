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

pub fn render_market_data_bars_table(payload: &Value, verbose: bool) -> String {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("bar_time"),
            Cell::new("symbol"),
            Cell::new("timeframe"),
            Cell::new("close"),
        ]);

    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let bar_time = as_str(item.get("bar_time"));
            let symbol = as_str(item.get("symbol"));
            let timeframe = as_str(item.get("timeframe"));
            let close = as_f64(item.get("close"));
            table.add_row(vec![bar_time, symbol, timeframe, close]);

            if verbose {
                let open = as_f64(item.get("open"));
                let high = as_f64(item.get("high"));
                let low = as_f64(item.get("low"));
                let volume = as_f64(item.get("volume"));
                let source = as_str(item.get("data_source"));
                table.add_row(vec![
                    "".to_string(),
                    format!("o/h/l={open}/{high}/{low}"),
                    format!("vol={volume}"),
                    format!("src={source}"),
                ]);
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

    format!(
        "日频管线摘要\n{}\n候选标的（最多5）\n{}\n因子可用性\n{}\n",
        summary, top, availability
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

    let recommended = as_str(
        payload
            .get("data")
            .and_then(|d| d.get("recommended_scheme")),
    );
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
        as_str(report.and_then(|r| r.get("summary")).and_then(|s| s.get("recommended_scheme"))),
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
        let name = as_str(item.get("name"));
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
