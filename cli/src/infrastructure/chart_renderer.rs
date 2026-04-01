use std::cmp::Ordering;

use serde_json::Value;
use textplots::{
    AxisBuilder, Chart, LabelBuilder, LineStyle, Plot, Shape, TickDisplay, TickDisplayBuilder,
};

fn supports_unicode() -> bool {
    let lang = std::env::var("LC_ALL")
        .or_else(|_| std::env::var("LC_CTYPE"))
        .or_else(|_| std::env::var("LANG"))
        .unwrap_or_default()
        .to_uppercase();
    lang.contains("UTF-8")
}

fn supports_ansi_color() -> bool {
    if std::env::var_os("NO_COLOR").is_some() {
        return false;
    }
    let term = std::env::var("TERM").unwrap_or_default().to_lowercase();
    !term.is_empty() && term != "dumb"
}

fn colorize(input: &str, ansi_code: &str, enable: bool) -> String {
    if enable {
        format!("\x1b[{ansi_code}m{input}\x1b[0m")
    } else {
        input.to_string()
    }
}

fn trend_ansi_code(first: f64, last: f64) -> &'static str {
    if last > first {
        "32" // green
    } else if last < first {
        "31" // red
    } else {
        "37" // gray/white
    }
}

fn downsample_for_chart(values: &[f64], target_points: usize) -> Vec<f64> {
    if values.len() <= target_points || target_points < 2 {
        return values.to_vec();
    }
    let last_index = values.len() - 1;
    let step = last_index as f64 / (target_points - 1) as f64;
    let mut sampled = Vec::with_capacity(target_points);
    let mut prev_idx: Option<usize> = None;
    for i in 0..target_points {
        let mut idx = (i as f64 * step).round() as usize;
        if idx > last_index {
            idx = last_index;
        }
        if prev_idx != Some(idx) {
            sampled.push(values[idx]);
            prev_idx = Some(idx);
        }
    }
    if sampled.last().copied() != Some(values[last_index]) {
        sampled.push(values[last_index]);
    }
    sampled
}

fn render_line_plot(values: &[f64], title: &str) -> String {
    if values.is_empty() {
        return format!("{title}\n(no data)\n");
    }
    if values.len() < 2 {
        return format!(
            "{title}\n(sample too small for line chart: n=1)\npoint: ● {}\n\n",
            values[0]
        );
    }
    let all_equal = values.windows(2).all(|w| w[0] == w[1]);
    if all_equal {
        return format!(
            "{title}\n(flat series, no visible slope)\nline : {}  ({})\n\n",
            "─".repeat(values.len().min(40)),
            values[0]
        );
    }

    const CHART_WIDTH: usize = 180;
    const CHART_HEIGHT: u32 = 30;
    let sampled_values = downsample_for_chart(values, CHART_WIDTH);
    let points: Vec<(f32, f32)> = sampled_values
        .iter()
        .enumerate()
        .map(|(i, v)| (i as f32, *v as f32))
        .collect();
    let xmax = (points.len() - 1) as f32;
    let min_v = values.iter().copied().fold(f64::INFINITY, f64::min);
    let max_v = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let span = (max_v - min_v).max(1.0);
    let ymin = (min_v - span * 0.08) as f32;
    let ymax = (max_v + span * 0.08) as f32;
    let chart_text = {
        let shape = Shape::Lines(&points);
        let mut chart = Chart::new_with_y_range(CHART_WIDTH as u32, CHART_HEIGHT, 0.0, xmax, ymin, ymax);
        let plotted = chart
            .lineplot(&shape)
            .x_axis_style(LineStyle::Solid)
            .y_axis_style(LineStyle::Solid)
            .y_tick_display(TickDisplay::Dense)
            .x_label_format(textplots::LabelFormat::Value)
            .y_label_format(textplots::LabelFormat::Value);
        plotted.borders();
        plotted.axis();
        plotted.figures();
        format!("{}", plotted)
    };
    let sample_note = if sampled_values.len() < values.len() {
        format!(
            "(downsampled for readability: {} -> {} points)\n",
            values.len(),
            sampled_values.len()
        )
    } else {
        String::new()
    };
    format!("{title}\n{sample_note}{chart_text}\n")
}

fn render_sparkline(values: &[f64]) -> String {
    if values.is_empty() {
        return "(no data)".to_string();
    }
    if values.len() == 1 {
        return "●".to_string();
    }
    let levels: [char; 8] = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];
    let min_v = values.iter().copied().fold(f64::INFINITY, f64::min);
    let max_v = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let span = (max_v - min_v).max(f64::EPSILON);
    let glyphs: Vec<char> = values
        .iter()
        .map(|v| {
            let normalized = ((*v - min_v) / span).clamp(0.0, 1.0);
            let idx = (normalized * (levels.len() - 1) as f64).round() as usize;
            levels[idx]
        })
        .collect();

    if !supports_ansi_color() {
        return glyphs.iter().collect();
    }

    let mut out = String::new();
    for (idx, ch) in glyphs.iter().enumerate() {
        let code = if idx == 0 {
            "37"
        } else if values[idx] > values[idx - 1] {
            "32"
        } else if values[idx] < values[idx - 1] {
            "31"
        } else {
            "37"
        };
        out.push_str(&colorize(&ch.to_string(), code, true));
    }
    out
}

pub fn render_sync_runs_chart(
    payload: &Value,
    symbol: &str,
    benchmark_symbol: Option<&str>,
) -> Result<String, String> {
    render_sync_runs_chart_with_capability(payload, supports_unicode(), symbol, benchmark_symbol)
}

pub fn extract_close_series_for_symbol(payload: &Value, symbol: &str) -> Vec<(String, f64)> {
    let mut points: Vec<(String, f64)> = Vec::new();
    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let sym = item.get("symbol").and_then(Value::as_str).unwrap_or("");
            if !sym.is_empty() && sym != symbol {
                continue;
            }
            let ts = item
                .get("bar_time")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let close = item.get("close").and_then(Value::as_f64).unwrap_or(0.0);
            if !ts.is_empty() {
                points.push((ts, close));
            }
        }
    }
    points.sort_by(|a, b| {
        if a.0 < b.0 {
            Ordering::Less
        } else if a.0 > b.0 {
            Ordering::Greater
        } else {
            Ordering::Equal
        }
    });
    points
}

pub fn render_sync_runs_chart_with_capability(
    payload: &Value,
    unicode_supported: bool,
    symbol: &str,
    benchmark_symbol: Option<&str>,
) -> Result<String, String> {
    if !unicode_supported {
        return Err("terminal does not support unicode chart characters".to_string());
    }

    let points = extract_close_series_for_symbol(payload, symbol);

    let mut out = String::new();
    let closes: Vec<f64> = points.iter().map(|(_, c)| *c).collect();
    let first_ts = points.first().map(|(t, _)| t.as_str()).unwrap_or("-");
    let last_ts = points.last().map(|(t, _)| t.as_str()).unwrap_or("-");

    out.push_str(&format!("Price Chart (textplots) - {symbol}\n"));
    if let Some(bm) = benchmark_symbol {
        out.push_str(&format!("Benchmark: {bm}\n"));
    }
    out.push_str(&format!("Range: {first_ts} -> {last_ts}\n"));
    out.push_str(&format!("Points: {}\n\n", points.len()));
    if let (Some(first), Some(last)) = (closes.first(), closes.last()) {
        let delta = last - first;
        let pct = if *first == 0.0 { 0.0 } else { delta / first * 100.0 };
        let summary = format!("Change: {:+.2} ({:+.2}%)", delta, pct);
        let trend_color = trend_ansi_code(*first, *last);
        out.push_str(&format!(
            "{}\n\n",
            colorize(&summary, trend_color, supports_ansi_color())
        ));
    }
    out.push_str(&format!(
        "Compact Trend: {}\n\n",
        render_sparkline(&closes)
    ));
    out.push_str(&render_line_plot(&closes, "Close Price"));

    if points.is_empty() {
        out.push_str("No data points.\n");
    }

    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::downsample_for_chart;

    #[test]
    fn downsample_keeps_first_and_last_points() {
        let source: Vec<f64> = (0..1000).map(|x| x as f64).collect();
        let sampled = downsample_for_chart(&source, 120);
        assert_eq!(sampled.first().copied(), Some(0.0));
        assert_eq!(sampled.last().copied(), Some(999.0));
        assert!(sampled.len() <= 121);
    }
}
