use crate::application::requests::PortfolioOptimizeRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(
    about = "L4 组合优化：从 L3 信号生成目标权重（需 quant HTTP 服务）"
)]
pub struct PortfolioArgs {
    #[command(subcommand)]
    pub command: PortfolioSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum PortfolioSubcommand {
    #[command(
        about = "均值-方差 QP 组合优化，返回 target_weights + optimization_report",
        long_about = "调用 POST /api/v1/portfolio/optimize。\
alpha 缺省时自动从 L3 signal snapshot 取 composite_score。\
目标函数：max αᵀw - λ_risk·wᵀΣw - λ_tc·Σ|wᵢ-w_prev|，含单标的/行业权重上限约束。\
求解失败时自动降级为等权或维持上期权重。"
    )]
    Optimize(OptimizeArgs),
}

const OPTIMIZE_AFTER_HELP: &str = "\
示例:
  hf portfolio optimize --as-of 2026-04-01
  hf portfolio optimize --as-of 2026-04-01 --output table

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- portfolio optimize --as-of 2026-04-01

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务（如 http://127.0.0.1:8000）";

#[derive(Debug, Args)]
#[command(after_long_help = OPTIMIZE_AFTER_HELP)]
pub struct OptimizeArgs {
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
        help = "输出形式：json = 标准 CLI envelope（默认）；table = 终端中文表格"
    )]
    pub output: String,
}

impl From<OptimizeArgs> for PortfolioOptimizeRequest {
    fn from(args: OptimizeArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
