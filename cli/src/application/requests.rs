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
}

#[derive(Debug, Clone)]
pub struct DataUniverseSyncRequest {
    pub universe: String,
    pub provider: String,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct DataQueryRequest {
    pub days: i32,
    pub timeframe: String,
    pub status: Option<String>,
    pub request_id: Option<String>,
    pub limit: Option<i32>,
    pub output: String,
    pub verbose: bool,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct DataBarsRequest {
    pub symbols: Option<String>,
    pub timeframe: String,
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub output: String,
    pub verbose: bool,
    pub no_benchmark: bool,
    pub limit: Option<i32>,
    pub timeout_ms: Option<u64>,
}

#[derive(Debug)]
pub enum AppCommand {
    PipelineDaily(PipelineDailyRequest),
    PipelineCompare(PipelineCompareRequest),
    FactorOptimize(FactorOptimizeRequest),
    FactorReplay(FactorReplayRequest),
    DataSync(DataSyncRequest),
    DataUniverseSync(DataUniverseSyncRequest),
    DataQuery(DataQueryRequest),
    DataBars(DataBarsRequest),
}
