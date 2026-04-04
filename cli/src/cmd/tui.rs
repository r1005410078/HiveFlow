use clap::Args;

/// 全屏终端界面：instruments 全列表 + 全 universe K 线；Tab/t 图/表；+/- 颗粒度
#[derive(Debug, Args)]
#[command(
    about = "交互式全屏：左侧 csi300 instruments；右侧近 7 日 K 线（默认分时 1m）；Tab/t 走势图/表格；+ 更细 − 更粗：分时→日K→周K→月K→年K；图内窗口缩放为 [/]；需 ~/.hiveflow/config.toml"
)]
pub struct TuiArgs {}
