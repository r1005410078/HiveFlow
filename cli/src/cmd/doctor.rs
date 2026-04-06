use crate::application::requests::DoctorRequest;
use clap::Args;

const DOCTOR_AFTER_HELP: &str = "\
检查本机 CLI 配置与 quant HTTP 服务是否可达（对 server_url 请求 GET /openapi.json）。\n\
不访问业务 API，无需数据库。\n\
\n\
示例:\n\
  hf doctor\n\
  hf doctor --output json\n\
\n\
  仓库内开发:\n\
  cargo run -p hf-cli -- doctor --output json\n\
\n\
前置:\n\
  默认读取 ~/.hiveflow/config.toml（与多数子命令一致）";

#[derive(Debug, Args)]
#[command(after_long_help = DOCTOR_AFTER_HELP)]
pub struct DoctorArgs {
    #[arg(
        long,
        default_value = "table",
        value_name = "MODE",
        help = "输出形式：table = 终端摘要（默认）；json = 标准 CLI envelope"
    )]
    pub output: String,
    #[arg(
        long,
        help = "探测 quant 时的 HTTP 超时（毫秒）；缺省使用配置文件中的 timeout_ms"
    )]
    pub timeout_ms: Option<u64>,
    #[arg(
        long,
        default_value_t = 7,
        value_name = "N",
        help = "拉取服务端 sync_runs 摘要时的回溯自然日窗（1–90，与 GET /v1/system/doctor 一致）"
    )]
    pub sync_days: i32,
}

impl From<DoctorArgs> for DoctorRequest {
    fn from(args: DoctorArgs) -> Self {
        Self {
            output: args.output,
            timeout_ms: args.timeout_ms,
            sync_days: args.sync_days.clamp(1, 90),
        }
    }
}
