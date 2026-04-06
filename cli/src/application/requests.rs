#[derive(Debug, Clone)]
pub struct PipelineDailyRequest {
    pub as_of: String,
    pub output: String,
}

#[derive(Debug, Clone)]
pub struct PipelineCompareRequest {
    pub start_date: String,
    pub end_date: String,
    pub top_n: usize,
    pub output: String,
}

#[derive(Debug, Clone)]
pub struct FactorOptimizeRequest {
    pub start_date: String,
    pub end_date: String,
    pub factor_names: Vec<String>,
    pub correlation_threshold: Option<f64>,
    pub output: String,
}

#[derive(Debug, Clone)]
pub struct FactorReplayRequest {
    pub start_date: String,
    pub end_date: String,
    pub factor_names: Vec<String>,
    pub correlation_threshold: Option<f64>,
    pub output: String,
}

#[derive(Debug, Clone)]
pub struct DataSyncRequest {
    pub days: i32,
    pub end_date: String,
    pub timeframe: String,
    pub symbols: Option<String>,
    pub universe: Option<String>,
    pub request_id: Option<String>,
    pub timeout_ms: Option<u64>,
    pub wait: bool,
    pub poll_interval_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct DataSyncCancelRequest {
    pub run_id: String,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct DataSyncRetryFailedRequest {
    pub from_run_id: String,
    pub timeout_ms: Option<u64>,
    pub wait: bool,
}

#[derive(Debug, Clone)]
pub struct DataUniverseSyncRequest {
    pub universe: String,
    pub provider: String,
    pub timeout_ms: Option<u64>,
    pub wait: bool,
    pub poll_interval_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct DataSymbolNamesSyncRequest {
    pub universes: Vec<String>,
    pub provider: String,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct TaskListRequest {
    pub days: i32,
    pub timeframe: String,
    pub status: Option<String>,
    pub request_id: Option<String>,
    pub limit: Option<i32>,
    pub output: String,
    pub verbose: bool,
    pub timeout_ms: Option<u64>,
}

/// `hf task progress`：查看运行中同步任务进度（列表发现或指定 run_id）
#[derive(Debug, Clone)]
pub struct TaskProgressRequest {
    pub run_id: Option<String>,
    pub days: i32,
    pub timeframe: Option<String>,
    pub limit: i32,
    pub output: String,
    pub verbose: bool,
    pub timeout_ms: Option<u64>,
    pub watch: bool,
    pub poll_interval_ms: Option<u64>,
}

/// `hf data query`：按窗口查 K 线（bars API）
#[derive(Debug, Clone)]
pub struct DataMarketQueryRequest {
    /// 与 end_date 一起确定窗口；若同时给了 start_date+end_date 则可忽略
    pub days: i32,
    pub end_date: Option<String>,
    pub start_date: Option<String>,
    pub symbols: Option<String>,
    pub universe: Option<String>,
    pub timeframe: String,
    pub limit: Option<i32>,
    pub output: String,
    pub verbose: bool,
    pub timeout_ms: Option<u64>,
}

/// `hf tui`：全屏行情预览（无额外参数）
#[derive(Debug, Clone, Default)]
pub struct TuiShellRequest {}

/// `hf data coverage`：universe 与库内 1d K 线覆盖对比
#[derive(Debug, Clone)]
pub struct DataCoverageRequest {
    pub universe: String,
    pub start_date: String,
    pub end_date: String,
    pub min_bars: Option<i32>,
    pub output: String,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct DataBarsRequest {
    pub symbols: Option<String>,
    pub universe: Option<String>,
    pub timeframe: String,
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub output: String,
    pub verbose: bool,
    pub no_benchmark: bool,
    pub limit: Option<i32>,
    /// TUI 每标的最大显示点数；`0` 表示不聚合。json/table 始终为原始 items。
    pub max_display_points: usize,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct SignalSnapshotRequest {
    pub as_of: String,
    pub output: String,
}

#[derive(Debug, Clone)]
pub struct SignalEvaluateRequest {
    pub start_date: String,
    pub end_date: String,
    pub forward_days: u32,
    pub output: String,
}

#[derive(Debug, Clone)]
pub struct PortfolioOptimizeRequest {
    pub as_of: String,
    pub output: String,
}

#[derive(Debug, Clone)]
pub struct RiskCheckRequest {
    pub as_of: String,
    pub output: String,
}

#[derive(Debug)]
pub enum AppCommand {
    Tui(TuiShellRequest),
    PipelineDaily(PipelineDailyRequest),
    PipelineCompare(PipelineCompareRequest),
    FactorOptimize(FactorOptimizeRequest),
    FactorReplay(FactorReplayRequest),
    DataSync(DataSyncRequest),
    DataSyncCancel(DataSyncCancelRequest),
    DataSyncRetryFailed(DataSyncRetryFailedRequest),
    DataUniverseSync(DataUniverseSyncRequest),
    DataSymbolNamesSync(DataSymbolNamesSyncRequest),
    TaskList(TaskListRequest),
    TaskProgress(TaskProgressRequest),
    TaskCancel(DataSyncCancelRequest),
    TaskRetryFailed(DataSyncRetryFailedRequest),
    DataQuery(DataMarketQueryRequest),
    DataBars(DataBarsRequest),
    DataCoverage(DataCoverageRequest),
    SignalSnapshot(SignalSnapshotRequest),
    SignalEvaluate(SignalEvaluateRequest),
    PortfolioOptimize(PortfolioOptimizeRequest),
    RiskCheck(RiskCheckRequest),
}
