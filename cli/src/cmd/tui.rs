use clap::Args;

/// 全屏终端界面：先拉服务端标的列表，再拉近窗 K 线（单标的跟随 bars 游标；需 TTY 与 quant）
#[derive(Debug, Args)]
#[command(
    about = "交互式全屏：左侧标的来自 GET /instruments，右侧 K 线默认 csi300 首只标的、近 7 日 1m；需 ~/.hiveflow/config.toml"
)]
pub struct TuiArgs {}
