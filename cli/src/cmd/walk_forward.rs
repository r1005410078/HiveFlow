use crate::application::requests::WalkForwardRequest;
use clap::Args;

#[derive(Debug, Args)]
pub struct WalkForwardArgs {
    /// Start date for walk-forward period (YYYY-MM-DD)
    #[arg(long)]
    pub start_date: String,

    /// End date for walk-forward period (YYYY-MM-DD)
    #[arg(long)]
    pub end_date: String,

    /// Calendar days for warm-up window (default: 180)
    #[arg(long, default_value_t = 180)]
    pub warm_up_days: u32,

    /// Calendar days for test window (default: 63)
    #[arg(long, default_value_t = 63)]
    pub test_window_days: u32,

    /// Calendar days to step forward each window (default: 21)
    #[arg(long, default_value_t = 21)]
    pub step_days: u32,

    /// Transaction cost in basis points (default: 0.0)
    #[arg(long, default_value_t = 0.0)]
    pub cost_bp: f64,

    /// Output format: json|table (default: json)
    #[arg(long, default_value = "json")]
    pub output: String,

    /// HTTP timeout in milliseconds (optional, uses config default if not provided)
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}

impl From<WalkForwardArgs> for WalkForwardRequest {
    fn from(args: WalkForwardArgs) -> Self {
        Self {
            start_date: args.start_date,
            end_date: args.end_date,
            warm_up_days: Some(args.warm_up_days),
            test_window_days: Some(args.test_window_days),
            step_days: Some(args.step_days),
            cost_bp: Some(args.cost_bp),
            output: args.output,
            timeout_ms: args.timeout_ms,
        }
    }
}
