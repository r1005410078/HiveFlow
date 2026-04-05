use clap::Args;

/// 全屏终端界面：instruments 全列表；选中标的 + 基准一次拉多周期 bundle；Tab/t 图/表；1–5 颗粒度
#[derive(Debug, Args)]
#[command(
    about = "交互式全屏：左侧 csi300 instruments（仅当前选中行显示最新价，其余为 —）；右侧为选中标的 + 沪深300 基准的近 7 日数据（默认分时 1m）；换标防抖后自动重拉 bundle，已加载标的内存缓存（最多 32 个）避免重复请求；R 手动刷新当前标的行情；换 1–5 颗粒度用本地缓存；Tab/t 走势图/表格；走势图内 +/- 窗口缩放，表格翻页用 [/]；需 ~/.hiveflow/config.toml"
)]
pub struct TuiArgs {}
