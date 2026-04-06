use crate::application::requests::ExecutionPlanRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(about = "L6 执行计划：目标权重 → 预交易 → 订单列表（需 quant HTTP 服务）")]
pub struct ExecutionArgs {
    #[command(subcommand)]
    pub command: ExecutionSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum ExecutionSubcommand {
    #[command(
        about = "生成限价日单执行计划（三跳：L4 → L5.5 → L6）",
        long_about = "调用 POST /v1/execution/plan；\
先 POST /api/v1/portfolio/optimize 与 POST /api/v1/pretrade/check；\
名义资金 Phase 1 固定 1_000_000 CNY。"
    )]
    Plan(PlanArgs),
}

const PLAN_AFTER_HELP: &str = "\
示例:
  hf execution plan --as-of 2026-04-01
  hf execution plan --as-of 2026-04-01 --output json

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- execution plan --as-of 2026-04-01

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务（如 http://127.0.0.1:8000）";

#[derive(Debug, Args)]
#[command(after_long_help = PLAN_AFTER_HELP)]
pub struct PlanArgs {
    #[arg(
        long,
        value_name = "YYYY-MM-DD",
        help = "截面日期（PIT：只使用该日及之前已发布/可得的数据）"
    )]
    pub as_of: String,
    #[arg(
        long,
        default_value = "table",
        value_name = "MODE",
        help = "输出形式：table = 终端可读（默认）；json = 标准 CLI envelope"
    )]
    pub output: String,
}

impl From<PlanArgs> for ExecutionPlanRequest {
    fn from(args: PlanArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
