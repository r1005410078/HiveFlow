use crate::application::requests::{
    ConfigGetRequest, ConfigListRequest, ConfigSnapshotRequest,
};
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
#[command(about = "G2 实验治理：参数版本快照（需 quant HTTP 服务与 DB）")]
pub struct ConfigArgs {
    #[command(subcommand)]
    pub command: ConfigSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum ConfigSubcommand {
    #[command(about = "将当前硬编码策略参数写入 experiment_configs")]
    Snapshot(ConfigSnapshotCliArgs),
    #[command(about = "列出历史快照")]
    List(ConfigListCliArgs),
    #[command(about = "按 config_id 查询明细")]
    Get(ConfigGetCliArgs),
}

#[derive(Debug, Args)]
pub struct ConfigSnapshotCliArgs {
    #[arg(long, default_value = "", help = "备注")]
    pub note: String,
    #[arg(
        long,
        default_value = "table",
        value_name = "MODE",
        help = "输出：table（默认）| json"
    )]
    pub output: String,
    #[arg(long, help = "HTTP 超时（毫秒），缺省使用配置")]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Args)]
pub struct ConfigListCliArgs {
    #[arg(long, help = "仅列出包含该 layer 行的快照（如 l5.5）")]
    pub layer: Option<String>,
    #[arg(long, default_value_t = 20, help = "最大条数")]
    pub limit: u32,
    #[arg(
        long,
        default_value = "table",
        value_name = "MODE",
        help = "输出：table（默认）| json"
    )]
    pub output: String,
    #[arg(long, help = "HTTP 超时（毫秒），缺省使用配置")]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Args)]
pub struct ConfigGetCliArgs {
    #[arg(long, value_name = "UUID", help = "快照 config_id")]
    pub config_id: String,
    #[arg(
        long,
        default_value = "table",
        value_name = "MODE",
        help = "输出：table（默认）| json"
    )]
    pub output: String,
    #[arg(long, help = "HTTP 超时（毫秒），缺省使用配置")]
    pub timeout_ms: Option<u64>,
}

impl From<ConfigSnapshotCliArgs> for ConfigSnapshotRequest {
    fn from(args: ConfigSnapshotCliArgs) -> Self {
        Self {
            note: args.note,
            output: args.output,
            timeout_ms: args.timeout_ms,
        }
    }
}

impl From<ConfigListCliArgs> for ConfigListRequest {
    fn from(args: ConfigListCliArgs) -> Self {
        Self {
            layer: args.layer,
            limit: args.limit,
            output: args.output,
            timeout_ms: args.timeout_ms,
        }
    }
}

impl From<ConfigGetCliArgs> for ConfigGetRequest {
    fn from(args: ConfigGetCliArgs) -> Self {
        Self {
            config_id: args.config_id,
            output: args.output,
            timeout_ms: args.timeout_ms,
        }
    }
}
