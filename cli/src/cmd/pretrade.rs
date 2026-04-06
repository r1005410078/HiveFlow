use crate::application::requests::PretradeCheckRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(about = "L5.5 预交易模拟：冲击与可成交性估算（需 quant HTTP 服务）")]
pub struct PretradeArgs {
    #[command(subcommand)]
    pub command: PretradeSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum PretradeSubcommand {
    #[command(
        about = "基于 L4 目标权重估算市场冲击（bp）与参与度是否超过 10% ADV",
        long_about = "调用 POST /api/v1/pretrade/check。\
先通过 POST /api/v1/portfolio/optimize 获取目标权重；\
名义资金 Phase 1 固定 1_000_000 CNY。"
    )]
    Check(CheckArgs),
}

const CHECK_AFTER_HELP: &str = "\
示例:
  hf pretrade check --as-of 2026-04-01
  hf pretrade check --as-of 2026-04-01 --output json

  仓库内开发（包名 hf-cli）:
  cargo run -p hf-cli -- pretrade check --as-of 2026-04-01

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
        default_value = "table",
        value_name = "MODE",
        help = "输出形式：table = 终端可读（默认）；json = 标准 CLI envelope"
    )]
    pub output: String,
}

impl From<CheckArgs> for PretradeCheckRequest {
    fn from(args: CheckArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
