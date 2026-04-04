use crate::application::requests::RiskCheckRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(
    about = "L5 风险门控：对 L4 目标权重执行硬约束检查（需 quant HTTP 服务）"
)]
pub struct RiskArgs {
    #[command(subcommand)]
    pub command: RiskSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum RiskSubcommand {
    #[command(
        about = "执行风险门控检查，返回 risk_gate=pass|block + 四项检查明细",
        long_about = "调用 POST /api/v1/risk/check。\
自动从最新 L3 signal snapshot 获取目标权重（通过 L4 portfolio optimize 中转）。\
检测市场状态（normal/warning/crisis）并应用分态阈值，\
执行：组合年化波动率、单标的集中度、行业集中度、单日换手率四项检查。"
    )]
    Check(CheckArgs),
}

const CHECK_AFTER_HELP: &str = "\
示例:
  hf risk check --as-of 2026-04-04
  hf risk check --as-of 2026-04-04 --output table

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- risk check --as-of 2026-04-04

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务（如 http://127.0.0.1:8000）";

#[derive(Debug, Args)]
#[command(after_long_help = CHECK_AFTER_HELP)]
pub struct CheckArgs {
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
        help = "输出形式：json = 标准 CLI envelope（默认）；table = 终端表格"
    )]
    pub output: String,
}

impl From<CheckArgs> for RiskCheckRequest {
    fn from(args: CheckArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
