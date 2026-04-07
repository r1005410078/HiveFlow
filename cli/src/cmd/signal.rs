use crate::application::requests::{SignalEvaluateRequest, SignalSnapshotRequest};
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(
    about = "L3 信号工程：将 L2 因子截面标准化为 signal_matrix（需 quant HTTP 服务）"
)]
pub struct SignalArgs {
    #[command(subcommand)]
    pub command: SignalSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum SignalSubcommand {
    #[command(
        about = "请求服务端计算指定日期的标准化信号矩阵，并打印 JSON 或表格",
        long_about = "调用 POST /api/v1/signal/snapshot。\
标的池始终包含服务端 `quant/config/universes/default.txt`，可用多次 `--universe NAME` 合并其它池。\
data 为对象：signal_matrix（rows、composite_scores、transform_stats）\
与可选 technical.ma5_ma10（服务端有 bar 时）。\
l2_decision / 排序逻辑不受影响，本命令仅用于观测与联调。"
    )]
    Snapshot(SnapshotArgs),

    #[command(
        about = "评估 L3 信号质量：Rank IC（per-factor + composite）+ 漂移检测",
        long_about = "调用 POST /api/v1/signal/evaluate。\
遍历日期范围逐日重算信号并计算 T+N 收益的 Spearman Rank IC，\
同时检测信号分布漂移。需要 DB 中的真实 bar 数据。"
    )]
    Evaluate(EvaluateArgs),
}

const SNAPSHOT_AFTER_HELP: &str = "\
示例:
  hf signal snapshot --as-of 2026-04-01
  hf signal snapshot --as-of 2026-04-01 --output table
  hf signal snapshot --as-of 2026-04-01 --universe self_select --universe follow

  标的池：始终包含 quant/config/universes/default.txt，可用多次 --universe 追加合并。

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- signal snapshot --as-of 2026-04-01
  cargo run -p hf-cli -- signal snapshot --as-of 2026-04-01 --output json

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务（如 http://127.0.0.1:8000）";

#[derive(Debug, Args)]
#[command(after_long_help = SNAPSHOT_AFTER_HELP)]
pub struct SnapshotArgs {
    #[arg(
        long,
        value_name = "YYYY-MM-DD",
        help = "截面日期（PIT：只使用该日及之前已发布/可得的数据）"
    )]
    pub as_of: String,
    #[arg(
        long = "universe",
        value_name = "NAME",
        help = "与 default 合并的额外标的池（可多次指定；仅服务端 quant/config/universes/{name}.txt）"
    )]
    pub universes: Vec<String>,
    #[arg(
        long,
        default_value = "json",
        value_name = "MODE",
        help = "输出形式：json = 标准 CLI envelope（默认）；table = 终端中文表（概要 + 明细 + 综合分）"
    )]
    pub output: String,
}

const EVALUATE_AFTER_HELP: &str = "\
示例:
  hf signal evaluate --start-date 2026-03-01 --end-date 2026-04-01
  hf signal evaluate --start-date 2026-03-01 --end-date 2026-04-01 --forward-days 3 --output table

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- signal evaluate --start-date 2026-03-01 --end-date 2026-04-01

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务；
  需要 DB 中有真实 bar 数据（make db-up && make run-server）";

#[derive(Debug, Args)]
#[command(after_long_help = EVALUATE_AFTER_HELP)]
pub struct EvaluateArgs {
    #[arg(long, value_name = "YYYY-MM-DD", help = "评估起始日期")]
    pub start_date: String,
    #[arg(long, value_name = "YYYY-MM-DD", help = "评估结束日期")]
    pub end_date: String,
    #[arg(long, default_value = "1", help = "前瞻天数（默认 1）")]
    pub forward_days: u32,
    #[arg(long, default_value = "json", value_name = "MODE", help = "输出形式：json | table")]
    pub output: String,
}

impl From<SnapshotArgs> for SignalSnapshotRequest {
    fn from(args: SnapshotArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
            universes: args.universes,
        }
    }
}

impl From<EvaluateArgs> for SignalEvaluateRequest {
    fn from(args: EvaluateArgs) -> Self {
        Self {
            start_date: args.start_date,
            end_date: args.end_date,
            forward_days: args.forward_days,
            output: args.output,
        }
    }
}
