use std::collections::BTreeMap;
use std::io::{self, stdout};
use std::time::Duration;

use crossterm::{
    event::{self, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Alignment, Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    symbols,
    text::{Line, Span},
    widgets::{
        Axis, Block, Borders, Cell, Chart, Clear, Dataset, List, ListItem, ListState, Paragraph,
        Row, Table,
    },
    Terminal,
};
use serde_json::Value;

/// 全屏 K 线 TUI 终端句柄（raw mode + alternate screen）。由 [`sync_runs_tui_enter`] 创建，结束时须 [`sync_runs_tui_leave`]。
pub type SyncRunsTuiTerminal = Terminal<CrosstermBackend<io::Stdout>>;

/// 进入 raw mode 与 alternate screen，供多次 [`run_sync_runs_tui_iteration`] 复用（切换颗粒度时不应反复 enter/leave）。
pub fn sync_runs_tui_enter() -> Result<SyncRunsTuiTerminal, String> {
    enable_raw_mode().map_err(|e| format!("enable raw mode failed: {e}"))?;
    let mut out = stdout();
    execute!(out, EnterAlternateScreen).map_err(|e| format!("enter alt screen failed: {e}"))?;
    let backend = CrosstermBackend::new(out);
    Terminal::new(backend).map_err(|e| format!("create terminal failed: {e}"))
}

/// 与 [`sync_runs_tui_enter`] 配对；离开全屏并恢复终端状态。
pub fn sync_runs_tui_leave(terminal: &mut SyncRunsTuiTerminal) {
    let _ = disable_raw_mode();
    let _ = execute!(terminal.backend_mut(), LeaveAlternateScreen);
    let _ = terminal.show_cursor();
}

const TUI_LOADING_SPINNER: &[&str] =
    &["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

/// 全屏清屏并绘制加载行（切换颗粒度拉数时由 application 轮询调用以显示动画）。
pub fn sync_runs_tui_draw_loading(
    terminal: &mut SyncRunsTuiTerminal,
    detail: &str,
    tick: usize,
) -> Result<(), String> {
    let spin = TUI_LOADING_SPINNER[tick % TUI_LOADING_SPINNER.len()];
    let line = format!("{spin}  加载行情…  {detail}");
    terminal
        .draw(move |f| {
            let a = f.area();
            f.render_widget(Clear, a);
            let p = Paragraph::new(line)
                .alignment(Alignment::Center)
                .style(Style::default().fg(Color::Cyan));
            f.render_widget(p, a);
        })
        .map(|_| ())
        .map_err(|e| format!("draw loading failed: {e}"))
}

/// 在已打开的会话中跑一轮事件循环，直到用户退出或切换颗粒度（不关闭 alternate screen）。
pub fn run_sync_runs_tui_iteration(
    terminal: &mut SyncRunsTuiTerminal,
    payload: &Value,
    preferred_symbol: Option<&str>,
    benchmark_symbol: Option<&str>,
    timeframe_cycle: Option<(&[&str], &str)>,
) -> Result<SyncRunsTuiClose, String> {
    let symbols = build_symbol_series(payload);
    run_tui_loop(
        terminal,
        &symbols,
        payload,
        preferred_symbol,
        benchmark_symbol,
        timeframe_cycle,
    )
}

#[derive(Debug, Clone)]
struct SymbolSeries {
    symbol: String,
    /// Chinese short name from API (`symbol_name_zh`); may be empty.
    name_zh: String,
    points: Vec<(String, f64)>,
}

#[derive(Debug, Clone)]
struct ChartViewState {
    cursor: usize,
    window_start: usize,
    window_len: usize,
}

/// `render_sync_runs_tui_with_timeframes` 结束原因（`Quit` 或切换 K 线周期后由上层重新拉数）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SyncRunsTuiClose {
    Quit,
    TimeframeChanged {
        timeframe: String,
        /// 当前左侧选中的标的，供上层下一轮仍作为 `preferred_symbol`。
        selected_symbol: String,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum MainView {
    Chart,
    Table,
}

impl MainView {
    fn toggle(self) -> Self {
        match self {
            MainView::Chart => MainView::Table,
            MainView::Table => MainView::Chart,
        }
    }
}

impl ChartViewState {
    fn new(total: usize) -> Self {
        let default_window = total.clamp(40, 300);
        let window_start = total.saturating_sub(default_window);
        let cursor = total.saturating_sub(1);
        Self {
            cursor,
            window_start,
            window_len: default_window.max(1),
        }
    }

    fn normalize(&mut self, total: usize) {
        if total == 0 {
            self.cursor = 0;
            self.window_start = 0;
            self.window_len = 1;
            return;
        }
        self.window_len = self.window_len.clamp(1, total);
        self.cursor = self.cursor.min(total - 1);
        let max_start = total - self.window_len;
        self.window_start = self.window_start.min(max_start);
        let end = self.window_start + self.window_len - 1;
        if self.cursor < self.window_start {
            self.window_start = self.cursor;
        } else if self.cursor > end {
            self.window_start = self.cursor.saturating_sub(self.window_len - 1);
        }
    }

    fn cursor_left(&mut self, total: usize) {
        self.cursor = self.cursor.saturating_sub(1);
        self.normalize(total);
    }

    fn cursor_right(&mut self, total: usize) {
        self.cursor = (self.cursor + 1).min(total.saturating_sub(1));
        self.normalize(total);
    }

    fn pan_left(&mut self, total: usize) {
        self.window_start = self.window_start.saturating_sub(15);
        self.normalize(total);
    }

    fn pan_right(&mut self, total: usize) {
        self.window_start = (self.window_start + 15).min(total.saturating_sub(1));
        self.normalize(total);
    }

    fn zoom_in(&mut self, total: usize) {
        if self.window_len > 24 {
            self.window_len = (self.window_len / 2).max(24);
            self.normalize(total);
        }
    }

    fn zoom_out(&mut self, total: usize) {
        self.window_len = (self.window_len.saturating_mul(2)).min(total.max(1));
        self.normalize(total);
    }
}

/// Indices into `symbols` whose `symbol` or `name_zh` matches the trimmed query (substring, symbol ASCII-insensitive).
fn filtered_symbol_indices(symbols: &[SymbolSeries], query: &str) -> Vec<usize> {
    let q = query.trim();
    if q.is_empty() {
        return (0..symbols.len()).collect();
    }
    let q_lower = q.to_lowercase();
    symbols
        .iter()
        .enumerate()
        .filter(|(_, s)| {
            s.symbol.to_lowercase().contains(&q_lower) || s.name_zh.contains(q)
        })
        .map(|(i, _)| i)
        .collect()
}

#[derive(Debug, Clone)]
struct TuiState {
    /// Row index in the left list (into `filtered_indices`).
    selected_list_idx: usize,
    /// Subset of `symbols` indices to show; rebuilt when the filter query changes.
    filtered_indices: Vec<usize>,
    /// Substring filter for symbol code and Chinese short name.
    filter_query: String,
    /// When true, keyboard input edits `filter_query` instead of moving the chart.
    filter_editing: bool,
    chart_view: ChartViewState,
    show_benchmark: bool,
    main_view: MainView,
    /// Vertical scroll offset for table view (current symbol's bars).
    table_scroll: usize,
}

impl TuiState {
    fn new(
        symbols: &[SymbolSeries],
        preferred_symbol: Option<&str>,
        benchmark_enabled: bool,
    ) -> Self {
        let filter_query = String::new();
        let filtered_indices = filtered_symbol_indices(symbols, &filter_query);
        let selected_list_idx = preferred_symbol
            .and_then(|preferred| {
                filtered_indices
                    .iter()
                    .position(|&sym_i| symbols[sym_i].symbol == preferred)
            })
            .unwrap_or(0)
            .min(filtered_indices.len().saturating_sub(1));
        let points_len = filtered_indices
            .get(selected_list_idx)
            .and_then(|&i| symbols.get(i))
            .map(|s| s.points.len())
            .unwrap_or(0);
        Self {
            selected_list_idx,
            filtered_indices,
            filter_query,
            filter_editing: false,
            chart_view: ChartViewState::new(points_len),
            show_benchmark: benchmark_enabled,
            main_view: MainView::Chart,
            table_scroll: 0,
        }
    }

    fn current_symbol_index(&self) -> Option<usize> {
        self.filtered_indices.get(self.selected_list_idx).copied()
    }

    fn selected_series<'a>(&self, symbols: &'a [SymbolSeries]) -> Option<&'a SymbolSeries> {
        self.current_symbol_index()
            .and_then(|i| symbols.get(i))
    }

    fn apply_filter_update(&mut self, symbols: &[SymbolSeries]) {
        let prev_sym_i = self.current_symbol_index();
        self.filtered_indices = filtered_symbol_indices(symbols, &self.filter_query);
        self.table_scroll = 0;
        if self.filtered_indices.is_empty() {
            self.selected_list_idx = 0;
            self.chart_view = ChartViewState::new(0);
            self.chart_view.normalize(0);
            return;
        }
        self.selected_list_idx = prev_sym_i
            .and_then(|pi| self.filtered_indices.iter().position(|&i| i == pi))
            .unwrap_or(0)
            .min(self.filtered_indices.len().saturating_sub(1));
        self.reset_chart(symbols);
    }

    fn move_symbol_up(&mut self, symbols: &[SymbolSeries]) {
        if self.filtered_indices.is_empty() {
            return;
        }
        self.selected_list_idx = self.selected_list_idx.saturating_sub(1);
        self.table_scroll = 0;
        self.reset_chart(symbols);
    }

    fn move_symbol_down(&mut self, symbols: &[SymbolSeries]) {
        if self.filtered_indices.is_empty() {
            return;
        }
        self.selected_list_idx = (self.selected_list_idx + 1).min(self.filtered_indices.len() - 1);
        self.table_scroll = 0;
        self.reset_chart(symbols);
    }

    fn reset_chart(&mut self, symbols: &[SymbolSeries]) {
        let points_len = self
            .selected_series(symbols)
            .map(|s| s.points.len())
            .unwrap_or(0);
        self.chart_view = ChartViewState::new(points_len);
        self.chart_view.normalize(points_len);
    }
}

/// 左侧股票列表固定列宽（字符格）；右侧走势图占剩余宽度。
const TUI_STOCK_LIST_COL_WIDTH: u16 = 30;

/// 顶栏右侧：数字键快捷键与颗粒度档位（与 `TUI_TIMEFRAMES` 顺序一致；`[n]` 表示按该键）。
const TUI_TF_KEY_LEGEND: &str = "[1]分时 [2]日K [3]周K [4]月K [5]年K";

/// API `timeframe` → 界面用中文（K 线颗粒度）。
fn timeframe_label_zh(tf: &str) -> &'static str {
    match tf {
        "1m" => "分时",
        "1d" => "日K",
        "1w" => "周K",
        "1M" => "月K",
        "1y" => "年K",
        _ => "",
    }
}

fn tf_title_suffix(tf: &str) -> String {
    let zh = timeframe_label_zh(tf);
    if zh.is_empty() {
        format!(" ({tf})")
    } else {
        format!(" ({zh})")
    }
}

/// 底栏仅保留当前档位（颗粒度键位在顶栏右侧）。
fn timeframe_footer_hint(cycle: Option<(&[&str], &str)>) -> String {
    let Some((_choices, cur)) = cycle else {
        return String::new();
    };
    let z = timeframe_label_zh(cur);
    let cur_part = if z.is_empty() {
        cur.to_string()
    } else {
        format!("{z}·{cur}")
    };
    format!("  当前{}", cur_part)
}

fn selected_symbol_for_close(
    state: &TuiState,
    symbols: &[SymbolSeries],
    preferred_fallback: Option<&str>,
) -> String {
    state
        .selected_series(symbols)
        .map(|s| s.symbol.clone())
        .or_else(|| preferred_fallback.map(str::to_string))
        .or_else(|| symbols.first().map(|s| s.symbol.clone()))
        .unwrap_or_default()
}

fn filtered_items_payload(payload: &Value, symbol: &str) -> Value {
    let items: Vec<Value> = payload
        .get("items")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter(|it| {
                    it.get("symbol")
                        .and_then(Value::as_str)
                        .map(|s| s == symbol)
                        .unwrap_or(false)
                })
                .cloned()
                .collect()
        })
        .unwrap_or_default();
    serde_json::json!({ "items": items })
}

fn run_tui_loop(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
    symbols: &[SymbolSeries],
    bars_payload: &Value,
    preferred_symbol: Option<&str>,
    benchmark_symbol: Option<&str>,
    timeframe_cycle: Option<(&[&str], &str)>,
) -> Result<SyncRunsTuiClose, String> {
    let mut state = TuiState::new(symbols, preferred_symbol, benchmark_symbol.is_some());
    let tf_suffix: String = timeframe_cycle
        .map(|(_, c)| tf_title_suffix(c))
        .unwrap_or_default();
    let tf_bar_hint = timeframe_footer_hint(timeframe_cycle);

    loop {
        terminal
            .draw(|frame| {
                let area = frame.area();
                let show_tf_header = timeframe_cycle.is_some();
                let v_rows = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints(if show_tf_header {
                        vec![
                            Constraint::Length(1),
                            Constraint::Min(10),
                            Constraint::Length(2),
                        ]
                    } else {
                        vec![Constraint::Min(10), Constraint::Length(2)]
                    })
                    .split(area);

                let (main_row, hint_row) = if show_tf_header {
                    let header_r = v_rows[0];
                    let legend = Paragraph::new(Line::from(Span::styled(
                        TUI_TF_KEY_LEGEND,
                        Style::default().fg(Color::DarkGray),
                    )))
                    .alignment(Alignment::Right);
                    frame.render_widget(legend, header_r);
                    (v_rows[1], v_rows[2])
                } else {
                    (v_rows[0], v_rows[1])
                };

                if symbols.is_empty() {
                    let empty = Paragraph::new("没有可绘制数据，请先执行 data sync。")
                        .style(Style::default().fg(Color::Gray));
                    frame.render_widget(empty, main_row);
                    let hint = Paragraph::new("q/Esc/Enter 退出").style(Style::default().fg(Color::DarkGray));
                    frame.render_widget(hint, hint_row);
                    return;
                }

                let cols = Layout::default()
                    .direction(Direction::Horizontal)
                    .constraints([
                        Constraint::Length(TUI_STOCK_LIST_COL_WIDTH),
                        Constraint::Min(0),
                    ])
                    .split(main_row);

                let items: Vec<ListItem> = state
                    .filtered_indices
                    .iter()
                    .filter_map(|&idx| symbols.get(idx))
                    .map(|s| {
                        let latest = s.points.last().map(|(_, p)| *p).unwrap_or(0.0);
                        let name_tail: String = s.name_zh.chars().take(8).collect();
                        let left = if name_tail.is_empty() {
                            format!("{:<10}", s.symbol)
                        } else {
                            format!("{:<10} {}", s.symbol, name_tail)
                        };
                        ListItem::new(Line::from(vec![
                            Span::styled(left, Style::default().fg(Color::DarkGray)),
                            Span::styled(
                                format!("  {:>10.2}", latest),
                                Style::default().fg(Color::DarkGray),
                            ),
                        ]))
                    })
                    .collect();
                let mut list_state = ListState::default();
                list_state.select(if state.filtered_indices.is_empty() {
                    None
                } else {
                    Some(state.selected_list_idx)
                });
                let list_title = if state.filter_query.trim().is_empty() {
                    format!("Stocks ({})", symbols.len())
                } else {
                    format!(
                        "Stocks {}/{}",
                        state.filtered_indices.len(),
                        symbols.len()
                    )
                };
                let list = List::new(items)
                    .block(
                        Block::default()
                            .borders(Borders::NONE)
                            .title(list_title)
                            .title_style(Style::default().fg(Color::Gray)),
                    )
                    .highlight_style(
                        Style::default()
                            .fg(Color::LightYellow)
                            .add_modifier(Modifier::BOLD),
                    )
                    .highlight_symbol(">> ");
                frame.render_stateful_widget(list, cols[0], &mut list_state);

                if let Some(series) = state.selected_series(symbols) {
                    let points = &series.points;
                    let total = points.len();

                    if state.main_view == MainView::Table {
                        let sub = filtered_items_payload(bars_payload, series.symbol.as_str());
                        let bar_rows = collect_bars_table_rows(&sub, false);
                        let block = Block::default()
                            .title(format!(" Table — {} ", series.symbol))
                            .borders(Borders::ALL);
                        let inner = block.inner(cols[1]);
                        frame.render_widget(block, cols[1]);
                        let page = (inner.height as usize).saturating_sub(2).max(3);
                        let max_scroll =
                            bar_rows.len().saturating_sub(page.min(bar_rows.len()).max(1));
                        state.table_scroll = state.table_scroll.min(max_scroll);
                        if bar_rows.is_empty() {
                            let empty = Paragraph::new("该标的暂无 bar 行（与左侧列表同一 payload）。")
                                .style(Style::default().fg(Color::Yellow));
                            frame.render_widget(empty, inner);
                        } else {
                            let show_name = bar_rows.first().is_some_and(|r| r.len() >= 5);
                            let mut hdr = vec![Cell::from("bar_time"), Cell::from("symbol")];
                            if show_name {
                                hdr.push(Cell::from("名称"));
                            }
                            hdr.extend([Cell::from("tf"), Cell::from("close")]);
                            let header =
                                Row::new(hdr).style(Style::default().add_modifier(Modifier::BOLD));
                            let data_rows: Vec<Row> = bar_rows
                                .iter()
                                .skip(state.table_scroll)
                                .take(page)
                                .map(|r| {
                                    Row::new(
                                        r.iter()
                                            .map(|c| Cell::from(c.as_str()))
                                            .collect::<Vec<_>>(),
                                    )
                                })
                                .collect();
                            let widths: &[Constraint] = if show_name {
                                &[
                                    Constraint::Percentage(28),
                                    Constraint::Percentage(14),
                                    Constraint::Percentage(18),
                                    Constraint::Percentage(8),
                                    Constraint::Percentage(24),
                                ]
                            } else {
                                &[
                                    Constraint::Percentage(38),
                                    Constraint::Percentage(18),
                                    Constraint::Percentage(10),
                                    Constraint::Percentage(28),
                                ]
                            };
                            let table = Table::new(data_rows, widths)
                                .header(header)
                                .block(Block::default());
                            frame.render_widget(table, inner);
                        }
                        let shown_end = (state.table_scroll + page).min(bar_rows.len());
                        let hint = Paragraph::new(format!(
                            "Tab/t 走势图  PgUp/PgDn [ ] Home/End 翻页  |  行 {}-{} / {}{}",
                            if bar_rows.is_empty() {
                                0
                            } else {
                                state.table_scroll + 1
                            },
                            shown_end,
                            bar_rows.len(),
                            tf_bar_hint
                        ))
                        .style(Style::default().fg(Color::DarkGray));
                        frame.render_widget(hint, hint_row);
                    } else if total == 0 {
                        let msg = Paragraph::new(
                            "该标的暂无 K 线点（检查 data sync、timeframe 与日期窗）。",
                        )
                        .style(Style::default().fg(Color::Yellow));
                        frame.render_widget(msg, cols[1]);
                        let nav_hint = Paragraph::new(format!(
                            "标的: ↑/↓  Tab/t 表格  /:筛选  退出: q/Esc{}",
                            tf_bar_hint
                        ))
                        .style(Style::default().fg(Color::DarkGray));
                        frame.render_widget(nav_hint, hint_row);
                    } else {
                    let window_end = (state.chart_view.window_start + state.chart_view.window_len).min(total);
                    let visible = &points[state.chart_view.window_start..window_end];
                    let samples: Vec<(f64, f64)> = visible
                        .iter()
                        .enumerate()
                        .map(|(idx, (_, price))| (idx as f64, *price))
                        .collect();
                    let mut comparison_title: Option<String> = None;
                    let benchmark_samples = if state.show_benchmark {
                        benchmark_symbol
                        .and_then(|bm| {
                            if bm == series.symbol {
                                None
                            } else {
                                symbols.iter().find(|s| s.symbol == bm)
                            }
                        })
                        .and_then(|bm_series| {
                            build_aligned_indexed_samples(
                                visible,
                                &bm_series.points,
                                bm_series.symbol.as_str(),
                            )
                        })
                    } else {
                        None
                    };

                    let (plot_samples, plot_benchmark_samples) = if let Some((stock_idx, bench_idx, bm)) =
                        benchmark_samples
                    {
                        comparison_title =
                            Some(format!("Trend - {} vs {}{}", series.symbol, bm, tf_suffix));
                        (stock_idx, Some(bench_idx))
                    } else {
                        (samples.clone(), None)
                    };
                    let cursor_visible = state
                        .chart_view
                        .cursor
                        .saturating_sub(state.chart_view.window_start)
                        .min(plot_samples.len().saturating_sub(1));
                    let cursor_x = cursor_visible as f64;
                    let cursor_y = plot_samples.get(cursor_visible).map(|(_, p)| *p).unwrap_or(0.0);
                    let cursor_points = vec![(cursor_x, cursor_y)];
                    let (y_min, y_max) = compute_y_range_from_samples(
                        &plot_samples,
                        plot_benchmark_samples.as_deref(),
                    );
                    let x_end = if plot_samples.len() >= 2 {
                        (plot_samples.len() - 1) as f64
                    } else {
                        1.0
                    };
                    let x_end_idx = if plot_samples.len() >= 2 {
                        plot_samples.len() - 1
                    } else {
                        1
                    };
                    let cur_tf = timeframe_cycle.map(|(_, c)| c).unwrap_or("1d");
                    let format_ts = |ts: &str| -> String {
                        if cur_tf == "1m" {
                            // 2026-04-01T09:30:00+08:00 -> 09:30
                            if ts.len() >= 16 {
                                &ts[11..16]
                            } else {
                                ts
                            }
                        } else {
                            // 2026-04-01T15:00:00+08:00 -> 2026-04-01
                            if ts.len() >= 10 {
                                &ts[0..10]
                            } else {
                                ts
                            }
                        }.to_string()
                    };

                    let (cursor_ts, cursor_price) = points
                        .get(state.chart_view.cursor)
                        .map(|(t, p)| (t.as_str(), *p))
                        .unwrap_or(("-", 0.0));

                    let start_ts = format_ts(points.get(state.chart_view.window_start).map(|(t, _)| t.as_str()).unwrap_or(""));
                    let end_ts = format_ts(points.get(window_end.saturating_sub(1)).map(|(t, _)| t.as_str()).unwrap_or(""));
                    let cursor_ts_fmt = format_ts(cursor_ts);

                    let x_labels: Vec<Span<'static>> = if cursor_visible == 0 || cursor_visible == x_end_idx {
                        vec![
                            Span::raw(start_ts),
                            Span::raw(end_ts),
                        ]
                    } else {
                        vec![
                            Span::raw(start_ts),
                            Span::raw(cursor_ts_fmt),
                            Span::raw(end_ts),
                        ]
                    };
                    let y_labels: Vec<Span<'static>> = if (cursor_y - y_min).abs() < f64::EPSILON
                        || (cursor_y - y_max).abs() < f64::EPSILON
                    {
                        vec![
                            Span::raw(format!("{:.2}", y_min)),
                            Span::raw(format!("{:.2}", y_max)),
                        ]
                    } else {
                        vec![
                            Span::raw(format!("{:.2}", y_min)),
                            Span::raw(format!("{:.2}", cursor_y)),
                            Span::raw(format!("{:.2}", y_max)),
                        ]
                    };

                    let mut datasets: Vec<Dataset> = Vec::new();
                    datasets.push(
                        Dataset::default()
                            .name("Close")
                            .marker(symbols::Marker::Braille)
                            .style(Style::default().fg(Color::White))
                            .graph_type(ratatui::widgets::GraphType::Line)
                            .data(&plot_samples),
                    );
                    if let Some(bench) = plot_benchmark_samples.as_deref() {
                        datasets.push(
                            Dataset::default()
                                .name("Benchmark")
                                .marker(symbols::Marker::Braille)
                                .style(Style::default().fg(Color::Rgb(170, 150, 60)))
                                .graph_type(ratatui::widgets::GraphType::Line)
                                .data(bench),
                        );
                    }
                    datasets.push(
                        Dataset::default()
                            .name("Cursor")
                            .marker(symbols::Marker::Dot)
                            .style(Style::default().fg(Color::Green))
                            .graph_type(ratatui::widgets::GraphType::Scatter)
                            .data(&cursor_points),
                    );

                    let chart = Chart::new(datasets)
                        .block(
                            Block::default()
                                .borders(Borders::NONE)
                                .title(
                                    comparison_title.unwrap_or_else(|| {
                                        format!("Trend - {}{}", series.symbol, tf_suffix)
                                    }),
                                )
                                .title_style(Style::default().fg(Color::Gray)),
                        )
                        .x_axis(
                            Axis::default()
                                .title("")
                                .style(Style::default().fg(Color::DarkGray))
                                .bounds([0.0, x_end])
                                .labels(x_labels),
                        )
                        .y_axis(
                            Axis::default()
                                .title("")
                                .style(Style::default().fg(Color::DarkGray))
                                .bounds([y_min, y_max])
                                .labels(y_labels),
                        );
                    frame.render_widget(chart, cols[1]);
                    let nav_hint = if state.filter_editing {
                        format!(
                            "筛选: \"{}\" | Enter 结束编辑  Esc 清空并退出筛选  |  {} {:.2}  [{}..{}]{}{}",
                            state.filter_query,
                            cursor_ts,
                            cursor_price,
                            state.chart_view.window_start,
                            window_end.saturating_sub(1),
                            if plot_benchmark_samples.is_some() {
                                "  |  Benchmark normalized to 100"
                            } else {
                                ""
                            },
                            tf_bar_hint
                        )
                    } else {
                        format!(
                            "标的: ↑/↓  Tab/t 表格  /:筛选  图: ←/→  平移: a/d  缩放: +/-  基准: b  复位: 0  退出: q/Esc  |  {} {:.2}  [{}..{}]{}{}",
                            cursor_ts,
                            cursor_price,
                            state.chart_view.window_start,
                            window_end.saturating_sub(1),
                            if plot_benchmark_samples.is_some() {
                                "  |  Benchmark normalized to 100"
                            } else {
                                ""
                            },
                            tf_bar_hint
                        )
                    };
                    let hint = Paragraph::new(nav_hint).style(Style::default().fg(Color::DarkGray));
                    frame.render_widget(hint, hint_row);
                    }
                } else if !symbols.is_empty() && state.filtered_indices.is_empty() {
                    let msg = Paragraph::new(
                        "当前筛选无匹配标的。按 / 编辑关键词，或 Esc 清空筛选并退出编辑。",
                    )
                    .style(Style::default().fg(Color::Yellow));
                    frame.render_widget(msg, cols[1]);
                    let hint = if state.filter_editing {
                        Paragraph::new(format!(
                            "筛选: \"{}\" | Enter 结束  Esc 清空筛选",
                            state.filter_query
                        ))
                    } else {
                        Paragraph::new("按 / 打开筛选，或修改筛选条件。")
                    }
                    .style(Style::default().fg(Color::DarkGray));
                    frame.render_widget(hint, hint_row);
                }
            })
            .map_err(|e| format!("draw tui failed: {e}"))?;

        if event::poll(Duration::from_millis(200)).map_err(|e| format!("poll event failed: {e}"))?
        {
            if let Event::Key(key) = event::read().map_err(|e| format!("read event failed: {e}"))?
            {
                if state.filter_editing {
                    match key.code {
                        KeyCode::Esc => {
                            state.filter_query.clear();
                            state.apply_filter_update(symbols);
                            state.filter_editing = false;
                        }
                        KeyCode::Enter => state.filter_editing = false,
                        KeyCode::Backspace => {
                            state.filter_query.pop();
                            state.apply_filter_update(symbols);
                        }
                        KeyCode::Char(c) => {
                            state.filter_query.push(c);
                            state.apply_filter_update(symbols);
                        }
                        _ => {}
                    }
                } else if key.code == KeyCode::Char('q')
                    || key.code == KeyCode::Esc
                    || key.code == KeyCode::Enter
                {
                    return Ok(SyncRunsTuiClose::Quit);
                } else if key.code == KeyCode::Char('/') {
                    state.filter_editing = true;
                } else if key.code == KeyCode::Tab || key.code == KeyCode::Char('t') {
                    state.main_view = state.main_view.toggle();
                    state.table_scroll = 0;
                } else {
                    if let Some((choices, cur)) = timeframe_cycle {
                        if let KeyCode::Char(c) = key.code {
                            if ('1'..='5').contains(&c) {
                                let i = (c as u8 - b'1') as usize;
                                if i < choices.len() {
                                    let next = choices[i];
                                    if next != cur {
                                        let selected_symbol = selected_symbol_for_close(
                                            &state,
                                            symbols,
                                            preferred_symbol,
                                        );
                                        return Ok(SyncRunsTuiClose::TimeframeChanged {
                                            timeframe: next.to_string(),
                                            selected_symbol,
                                        });
                                    }
                                }
                            }
                        }
                    }
                    if state.main_view == MainView::Table {
                    let size = terminal
                        .size()
                        .map_err(|e| format!("terminal size: {e}"))?;
                    let page = (size.height.saturating_sub(5) as usize).max(3);
                    let rows_len = state
                        .selected_series(symbols)
                        .map(|s| {
                            let sub = filtered_items_payload(bars_payload, s.symbol.as_str());
                            collect_bars_table_rows(&sub, false).len()
                        })
                        .unwrap_or(0);
                    let max_scroll = rows_len.saturating_sub(page.min(rows_len).max(1));
                    match key.code {
                        KeyCode::PageDown | KeyCode::Char(']') | KeyCode::Char('}') => {
                            state.table_scroll = (state.table_scroll + page).min(max_scroll);
                        }
                        KeyCode::PageUp | KeyCode::Char('[') | KeyCode::Char('{') => {
                            state.table_scroll = state.table_scroll.saturating_sub(page);
                        }
                        KeyCode::Home => state.table_scroll = 0,
                        KeyCode::End => state.table_scroll = max_scroll,
                        KeyCode::Up | KeyCode::Char('k') => state.move_symbol_up(symbols),
                        KeyCode::Down | KeyCode::Char('j') => state.move_symbol_down(symbols),
                        _ => {}
                    }
                    } else {
                    let selected_points_len = state
                        .selected_series(symbols)
                        .map(|s| s.points.len())
                        .unwrap_or(0);
                    match key.code {
                        KeyCode::Up | KeyCode::Char('k') => state.move_symbol_up(symbols),
                        KeyCode::Down | KeyCode::Char('j') => state.move_symbol_down(symbols),
                        KeyCode::Left | KeyCode::Char('h') => {
                            state.chart_view.cursor_left(selected_points_len)
                        }
                        KeyCode::Right | KeyCode::Char('l') => {
                            state.chart_view.cursor_right(selected_points_len)
                        }
                        KeyCode::Char('a') => state.chart_view.pan_left(selected_points_len),
                        KeyCode::Char('d') => state.chart_view.pan_right(selected_points_len),
                        KeyCode::Char('+') | KeyCode::Char('=') => {
                            state.chart_view.zoom_in(selected_points_len)
                        }
                        KeyCode::Char('-') | KeyCode::Char('_') => {
                            state.chart_view.zoom_out(selected_points_len)
                        }
                        KeyCode::Char('b') => {
                            if benchmark_symbol.is_some() {
                                state.show_benchmark = !state.show_benchmark;
                            }
                        }
                        KeyCode::Char('0') => {
                            state.chart_view = ChartViewState::new(selected_points_len)
                        }
                        _ => {}
                    }
                    state.chart_view.normalize(selected_points_len);
                    }
                }
            }
        }
    }
}

/// Paged table TUI for merged bars `items` (from GET /v1/market-data/bars).
/// Keys: PgUp/PgDn or `[`/`]` page, Home/End, q/Esc/Enter exit.
pub fn render_market_data_bars_paged_table_tui(payload: &Value, verbose: bool) -> Result<(), String> {
    let rows = collect_bars_table_rows(payload, verbose);
    if rows.is_empty() {
        return Err("no bar rows to display".to_string());
    }

    enable_raw_mode().map_err(|e| format!("enable raw mode failed: {e}"))?;
    let mut stdout = std::io::stdout();
    execute!(stdout, EnterAlternateScreen).map_err(|e| format!("enter alt screen failed: {e}"))?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend).map_err(|e| format!("create terminal failed: {e}"))?;

    let mut offset: usize = 0;
    let mut quit = false;
    while !quit {
        let size = terminal.size().map_err(|e| format!("terminal size: {e}"))?;
        let page = (size.height.saturating_sub(5) as usize).max(3);
        let max_scroll = rows.len().saturating_sub(page.min(rows.len()).max(1));
        offset = offset.min(max_scroll);

        terminal
            .draw(|frame| {
                let area = frame.area();
                let chunks = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints([Constraint::Min(3), Constraint::Length(1)])
                    .split(area);
                let table_area = chunks[0];
                let hint_area = chunks[1];

                let block = Block::default()
                    .title(" Market bars (paged) ")
                    .borders(Borders::ALL);
                let inner = block.inner(table_area);
                frame.render_widget(block, table_area);

                let show_name = rows.first().is_some_and(|r| r.len() >= 5);
                let mut hdr = vec![
                    Cell::from("bar_time"),
                    Cell::from("symbol"),
                ];
                if show_name {
                    hdr.push(Cell::from("名称"));
                }
                hdr.extend([Cell::from("tf"), Cell::from("close")]);
                let header = Row::new(hdr).style(Style::default().add_modifier(Modifier::BOLD));
                let data_rows: Vec<Row> = rows
                    .iter()
                    .skip(offset)
                    .take(page)
                    .map(|r| {
                        Row::new(
                            r.iter()
                                .map(|c| Cell::from(c.as_str()))
                                .collect::<Vec<_>>(),
                        )
                    })
                    .collect();
                let shown = data_rows.len();

                let widths: &[Constraint] = if show_name {
                    &[
                        Constraint::Percentage(28),
                        Constraint::Percentage(14),
                        Constraint::Percentage(18),
                        Constraint::Percentage(8),
                        Constraint::Percentage(24),
                    ]
                } else {
                    &[
                        Constraint::Percentage(38),
                        Constraint::Percentage(18),
                        Constraint::Percentage(10),
                        Constraint::Percentage(28),
                    ]
                };
                let table = Table::new(data_rows, widths)
                    .header(header)
                    .block(Block::default());
                frame.render_widget(table, inner);

                let hint = format!(
                    "PgUp/PgDn [ ] Home/End | rows {}-{} / {} | q/Esc quit{}",
                    offset + 1,
                    offset + shown,
                    rows.len(),
                    if verbose { " | verbose" } else { "" }
                );
                let p = Paragraph::new(hint).style(Style::default().fg(Color::DarkGray));
                frame.render_widget(p, hint_area);
            })
            .map_err(|e| format!("draw failed: {e}"))?;

        if event::poll(Duration::from_millis(200)).map_err(|e| format!("poll: {e}"))? {
            if let Event::Key(key) = event::read().map_err(|e| format!("read key: {e}"))? {
                let page = (terminal.size().map_err(|e| format!("terminal size: {e}"))?
                    .height
                    .saturating_sub(5) as usize)
                    .max(3);
                let max_scroll = rows.len().saturating_sub(page.min(rows.len()).max(1));
                match key.code {
                    KeyCode::Char('q') | KeyCode::Esc | KeyCode::Enter => quit = true,
                    KeyCode::PageDown | KeyCode::Char(']') | KeyCode::Char('}') => {
                        offset = (offset + page).min(max_scroll);
                    }
                    KeyCode::PageUp | KeyCode::Char('[') | KeyCode::Char('{') => {
                        offset = offset.saturating_sub(page);
                    }
                    KeyCode::Home => offset = 0,
                    KeyCode::End => offset = max_scroll,
                    _ => {}
                }
            }
        }
    }

    let _ = disable_raw_mode();
    let _ = execute!(terminal.backend_mut(), LeaveAlternateScreen);
    let _ = terminal.show_cursor();
    Ok(())
}

fn collect_bars_table_rows(payload: &Value, verbose: bool) -> Vec<Vec<String>> {
    let mut out: Vec<Vec<String>> = Vec::new();
    let Some(items) = payload.get("items").and_then(Value::as_array) else {
        return out;
    };
    let show_name = items
        .iter()
        .any(|item| item.get("symbol_name_zh").is_some());
    for item in items {
        let bar_time = item
            .get("bar_time")
            .and_then(Value::as_str)
            .unwrap_or("-")
            .to_string();
        let symbol = item
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or("-")
            .to_string();
        let name_zh = item
            .get("symbol_name_zh")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let tf = item
            .get("timeframe")
            .and_then(Value::as_str)
            .unwrap_or("-")
            .to_string();
        let close = item
            .get("close")
            .and_then(Value::as_f64)
            .map(|v| format!("{v:.4}"))
            .unwrap_or_else(|| "-".to_string());
        let mut row = vec![bar_time, symbol];
        if show_name {
            row.push(name_zh);
        }
        row.extend([tf, close]);
        out.push(row);
        if verbose {
            let open = item.get("open").and_then(Value::as_f64);
            let high = item.get("high").and_then(Value::as_f64);
            let low = item.get("low").and_then(Value::as_f64);
            let vol = item.get("volume").and_then(Value::as_f64);
            let detail = format!(
                "o/h/l={}/{}/{} vol={}",
                open.map(|v| format!("{v:.2}")).unwrap_or_default(),
                high.map(|v| format!("{v:.2}")).unwrap_or_default(),
                low.map(|v| format!("{v:.2}")).unwrap_or_default(),
                vol.map(|v| format!("{v:.0}")).unwrap_or_default(),
            );
            let mut detail_row = vec!["".to_string(), detail];
            if show_name {
                detail_row.push(String::new());
            }
            detail_row.extend(["".to_string(), "".to_string()]);
            out.push(detail_row);
        }
    }
    out
}

pub fn render_sync_runs_tui(
    payload: &Value,
    preferred_symbol: Option<&str>,
    benchmark_symbol: Option<&str>,
) -> Result<(), String> {
    render_sync_runs_tui_with_timeframes(
        payload,
        preferred_symbol,
        benchmark_symbol,
        None,
    )
    .map(|_| ())
}

/// 与 [`render_sync_runs_tui`] 相同，但提供 `timeframe_cycle` 时：数字键 **`1`–`5`** 直接选 `choices[0..]` 对应颗粒度
///（须 **细→粗**，与阶梯下标一致），并以 [`SyncRunsTuiClose::TimeframeChanged`] 带回当前选中标的供上层保持左侧高亮；
/// 走势图内 **`+` / `−`** 为窗口缩放（表格模式翻页仍用 `[/]` 等）。
///
/// `hf tui` 使用 [`sync_runs_tui_enter`] + 多次 [`run_sync_runs_tui_iteration`]，切换颗粒度时不反复进出全屏，避免整屏闪烁。
pub fn render_sync_runs_tui_with_timeframes(
    payload: &Value,
    preferred_symbol: Option<&str>,
    benchmark_symbol: Option<&str>,
    timeframe_cycle: Option<(&[&str], &str)>,
) -> Result<SyncRunsTuiClose, String> {
    let mut terminal = sync_runs_tui_enter()?;
    let run_res = run_sync_runs_tui_iteration(
        &mut terminal,
        payload,
        preferred_symbol,
        benchmark_symbol,
        timeframe_cycle,
    );
    sync_runs_tui_leave(&mut terminal);
    run_res
}

fn build_symbol_series(payload: &Value) -> Vec<SymbolSeries> {
    let mut by_symbol: BTreeMap<String, (String, Vec<(String, f64)>)> = BTreeMap::new();
    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let symbol = item
                .get("symbol")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            let ts = item
                .get("bar_time")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let close = item.get("close").and_then(Value::as_f64).unwrap_or(0.0);
            let row_name = item
                .get("symbol_name_zh")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            if symbol.is_empty() || ts.is_empty() {
                continue;
            }
            let ent = by_symbol.entry(symbol).or_insert_with(|| (String::new(), Vec::new()));
            if ent.0.is_empty() && !row_name.is_empty() {
                ent.0 = row_name;
            }
            ent.1.push((ts, close));
        }
    }
    by_symbol
        .into_iter()
        .map(|(symbol, (name_zh, mut points))| {
            points.sort_by(|a, b| a.0.cmp(&b.0));
            SymbolSeries {
                symbol,
                name_zh,
                points,
            }
        })
        .collect()
}

fn compute_y_range_from_samples(
    primary: &[(f64, f64)],
    secondary: Option<&[(f64, f64)]>,
) -> (f64, f64) {
    if primary.is_empty() {
        return (0.0, 1.0);
    }
    let mut min = primary.iter().map(|(_, v)| *v).fold(f64::INFINITY, f64::min);
    let mut max = primary
        .iter()
        .map(|(_, v)| *v)
        .fold(f64::NEG_INFINITY, f64::max);
    if let Some(other) = secondary {
        min = min.min(other.iter().map(|(_, v)| *v).fold(f64::INFINITY, f64::min));
        max = max.max(other.iter().map(|(_, v)| *v).fold(f64::NEG_INFINITY, f64::max));
    }
    let span = (max - min).max(1e-6);
    (min - span * 0.08, max + span * 0.08)
}

fn build_aligned_indexed_samples(
    stock_visible: &[(String, f64)],
    benchmark_points: &[(String, f64)],
    benchmark_symbol: &str,
) -> Option<(Vec<(f64, f64)>, Vec<(f64, f64)>, String)> {
    let bench_map: BTreeMap<&str, f64> = benchmark_points
        .iter()
        .map(|(ts, p)| (ts.as_str(), *p))
        .collect();
    let mut stock_raw: Vec<f64> = Vec::new();
    let mut bench_raw: Vec<f64> = Vec::new();
    for (ts, sp) in stock_visible {
        if let Some(bp) = bench_map.get(ts.as_str()) {
            stock_raw.push(*sp);
            bench_raw.push(*bp);
        }
    }
    if stock_raw.len() < 2 || bench_raw.len() < 2 {
        return None;
    }
    let s0 = stock_raw[0];
    let b0 = bench_raw[0];
    if s0 == 0.0 || b0 == 0.0 {
        return None;
    }
    let stock_idx: Vec<(f64, f64)> = stock_raw
        .iter()
        .enumerate()
        .map(|(i, v)| (i as f64, v / s0 * 100.0))
        .collect();
    let bench_idx: Vec<(f64, f64)> = bench_raw
        .iter()
        .enumerate()
        .map(|(i, v)| (i as f64, v / b0 * 100.0))
        .collect();
    Some((stock_idx, bench_idx, benchmark_symbol.to_string()))
}

#[cfg(test)]
mod tests {
    use super::{build_symbol_series, ChartViewState, SymbolSeries, TuiState};
    use serde_json::json;

    #[test]
    fn build_symbol_series_groups_and_sorts() {
        let payload = json!({
            "items": [
                {"symbol":"600519.SH","bar_time":"2026-04-02T09:32:00+08:00","close":1451.0},
                {"symbol":"000001.SZ","bar_time":"2026-04-02T09:31:00+08:00","close":12.1},
                {"symbol":"600519.SH","bar_time":"2026-04-02T09:31:00+08:00","close":1450.0}
            ]
        });
        let series = build_symbol_series(&payload);
        assert_eq!(series.len(), 2);
        assert_eq!(series[1].symbol, "600519.SH");
        assert_eq!(series[1].points[0].0, "2026-04-02T09:31:00+08:00");
    }

    #[test]
    fn tui_state_prefers_given_symbol() {
        let payload = json!({
            "items": [
                {"symbol":"000001.SZ","bar_time":"2026-04-02T09:31:00+08:00","close":12.1},
                {"symbol":"600519.SH","bar_time":"2026-04-02T09:31:00+08:00","close":1450.0}
            ]
        });
        let series = build_symbol_series(&payload);
        let state = TuiState::new(&series, Some("600519.SH"), true);
        let idx = state.filtered_indices[state.selected_list_idx];
        assert_eq!(series[idx].symbol, "600519.SH");
    }

    #[test]
    fn filtered_symbol_indices_matches_symbol_or_name() {
        let series = vec![
            SymbolSeries {
                symbol: "600519.SH".to_string(),
                name_zh: "贵州茅台".to_string(),
                points: vec![],
            },
            SymbolSeries {
                symbol: "000001.SZ".to_string(),
                name_zh: "平安银行".to_string(),
                points: vec![],
            },
        ];
        assert_eq!(super::filtered_symbol_indices(&series, ""), vec![0, 1]);
        assert_eq!(super::filtered_symbol_indices(&series, "600519"), vec![0]);
        assert_eq!(super::filtered_symbol_indices(&series, "600519.sh"), vec![0]);
        assert_eq!(super::filtered_symbol_indices(&series, "茅台"), vec![0]);
        assert_eq!(super::filtered_symbol_indices(&series, "银行"), vec![1]);
        assert!(super::filtered_symbol_indices(&series, "nomatch").is_empty());
    }

    #[test]
    fn tui_state_filter_update_preserves_selection_when_possible() {
        let series = vec![
            SymbolSeries {
                symbol: "000001.SZ".to_string(),
                name_zh: "".to_string(),
                points: vec![("t".to_string(), 1.0)],
            },
            SymbolSeries {
                symbol: "600519.SH".to_string(),
                name_zh: "".to_string(),
                points: vec![("t".to_string(), 2.0)],
            },
        ];
        let mut state = TuiState::new(&series, Some("600519.SH"), false);
        state.filter_query = "600519".to_string();
        state.apply_filter_update(&series);
        assert_eq!(state.filtered_indices.len(), 1);
        assert_eq!(series[state.filtered_indices[state.selected_list_idx]].symbol, "600519.SH");
    }

    #[test]
    fn chart_view_keeps_cursor_in_bounds() {
        let mut view = ChartViewState {
            cursor: 99,
            window_start: 0,
            window_len: 20,
        };
        view.normalize(100);
        assert!(view.cursor >= view.window_start);
        assert!(view.cursor < view.window_start + view.window_len);
    }
}
