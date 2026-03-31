#[derive(Debug, Clone)]
pub enum ErrorCode {
    DataFetchFailed,
    LowCoverage,
    SolverFallback,
    RiskGateBlocked,
    ExecutionPrecheckFailed,
}
