use crate::application::requests::SignalSnapshotRequest;
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
data 内为 signal_matrix：含 rows（逐标的×因子信号）、composite_scores（等权综合分）、\
transform_stats（去极值前后诊断）。\
l2_decision / 排序逻辑不受影响，本命令仅用于观测与联调。"
    )]
    Snapshot(SnapshotArgs),
}

const SNAPSHOT_AFTER_HELP: &str = "\
示例:
  hf signal snapshot --as-of 2026-04-01
  hf signal snapshot --as-of 2026-04-01 --output table

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
        long,
        default_value = "json",
        value_name = "MODE",
        help = "输出形式：json = 标准 CLI envelope（默认）；table = 终端中文表（概要 + 明细 + 综合分）"
    )]
    pub output: String,
}

impl From<SnapshotArgs> for SignalSnapshotRequest {
    fn from(args: SnapshotArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
