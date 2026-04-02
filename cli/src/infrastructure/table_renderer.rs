use comfy_table::presets::UTF8_FULL;
use comfy_table::{Cell, ContentArrangement, Table};
use serde_json::Value;

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

fn first_top_candidate_symbol(item: Option<&Value>) -> String {
    item.and_then(|version| version.get("top_candidates"))
        .and_then(Value::as_array)
        .and_then(|items| items.first())
        .and_then(|candidate| candidate.get("symbol"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string()
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

    format!(
        "版本对比回放\n版本对比汇总\n{}\n逐日明细\n{}\n",
        summary, daily
    )
}
