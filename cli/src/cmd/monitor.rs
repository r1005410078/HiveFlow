use crate::application::requests::MonitorHealthReportRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(about = "L8 监控复盘：因子/信号/风控健康报告（需 quant HTTP 服务）")]
pub struct MonitorArgs {
    #[command(subcommand)]
    pub command: MonitorSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum MonitorSubcommand {
    #[command(
        about = "生成指定截面的健康报告（green/yellow/red）",
        long_about = "调用 GET /v1/monitor/health-report，基于 run_daily 输出聚合，不重复计算因子。"
    )]
    HealthReport(HealthReportArgs),
}

const HEALTH_REPORT_AFTER_HELP: &str = "\
示例:
  hf monitor health-report --as-of 2026-04-01
  hf monitor health-report --as-of 2026-04-01 --output json

  仓库内开发:
  cargo run -p hf-cli -- monitor health-report --as-of 2026-04-01

前置:
  ~/.hiveflow/config.toml 中 server_url 指向已启动的 quant 服务";

#[derive(Debug, Args)]
#[command(after_long_help = HEALTH_REPORT_AFTER_HELP)]
pub struct HealthReportArgs {
    #[arg(
        long,
        value_name = "YYYY-MM-DD",
        help = "截面日期（与 run_daily 一致）"
    )]
    pub as_of: String,
    #[arg(
        long,
        default_value = "table",
        value_name = "MODE",
        help = "输出形式：table = 终端摘要（默认）；json = 标准 CLI envelope"
    )]
    pub output: String,
    #[arg(long, help = "HTTP 超时（毫秒），缺省使用配置")]
    pub timeout_ms: Option<u64>,
}

impl From<HealthReportArgs> for MonitorHealthReportRequest {
    fn from(args: HealthReportArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
            timeout_ms: args.timeout_ms,
        }
    }
}
