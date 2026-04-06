pub mod config;
pub mod data;
pub mod doctor;
pub mod execution;
pub mod factor;
pub mod monitor;
pub mod pipeline;
pub mod portfolio;
pub mod pretrade;
pub mod risk;
pub mod signal;
pub mod task;
pub mod tui;
pub mod walk_forward;

use crate::application::requests::AppCommand;
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(name = "hf")]
#[command(about = "HiveFlow CLI")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Debug, Subcommand)]
pub enum Commands {
    /// 本机配置与 quant 服务连通性自检（GET /openapi.json）
    Doctor(doctor::DoctorArgs),
    /// 全屏 TUI：instruments + bars（需 TTY）
    Tui(tui::TuiArgs),
    Pipeline(pipeline::PipelineArgs),
    Factor(factor::FactorArgs),
    Data(data::DataArgs),
    /// 异步任务：同步 run 列表、取消、失败重试
    Task(task::TaskArgs),
    /// L3 信号工程：因子截面 → signal_matrix（需 quant 服务与 ~/.hiveflow/config.toml）
    Signal(signal::SignalArgs),
    /// L4 组合优化：信号 → 目标权重（需 quant 服务与 ~/.hiveflow/config.toml）
    Portfolio(portfolio::PortfolioArgs),
    /// L5 风险门控：目标权重硬约束检查（需 quant 服务与 ~/.hiveflow/config.toml）
    Risk(risk::RiskArgs),
    /// L5.5 预交易模拟：冲击与可成交性（需 quant 服务与 ~/.hiveflow/config.toml）
    Pretrade(pretrade::PretradeArgs),
    /// L6 执行计划：订单列表（需 quant 服务与 ~/.hiveflow/config.toml）
    Execution(execution::ExecutionArgs),
    /// L7 walk-forward 回测：滚动窗口验证（需 quant 服务与 ~/.hiveflow/config.toml）
    WalkForward(walk_forward::WalkForwardArgs),
    /// L8 监控：健康报告（需 quant 服务与 ~/.hiveflow/config.toml）
    Monitor(monitor::MonitorArgs),
    /// G2 实验治理：参数快照 list/get/snapshot（需 quant 服务与 DB）
    Config(config::ConfigArgs),
}

impl From<Cli> for AppCommand {
    fn from(cli: Cli) -> Self {
        match cli.command {
            Commands::Doctor(args) => AppCommand::Doctor(args.into()),
            Commands::Tui(_) => AppCommand::Tui(Default::default()),
            Commands::Pipeline(args) => match args.command {
                pipeline::PipelineSubcommand::Daily(daily) => {
                    AppCommand::PipelineDaily(daily.into())
                }
                pipeline::PipelineSubcommand::Compare(compare) => {
                    AppCommand::PipelineCompare(compare.into())
                }
            },
            Commands::Factor(args) => match args.command {
                factor::FactorSubcommand::Optimize(optimize) => {
                    AppCommand::FactorOptimize(optimize.into())
                }
                factor::FactorSubcommand::Replay(replay) => AppCommand::FactorReplay(replay.into()),
            },
            Commands::Data(args) => match args.command {
                data::DataSubcommand::Sync(sync_args) => AppCommand::DataSync(sync_args.into()),
                data::DataSubcommand::SyncCancel(args) => AppCommand::DataSyncCancel(args.into()),
                data::DataSubcommand::SyncRetryFailed(args) => {
                    AppCommand::DataSyncRetryFailed(args.into())
                }
                data::DataSubcommand::UniverseSync(sync_args) => {
                    AppCommand::DataUniverseSync(sync_args.into())
                }
                data::DataSubcommand::SymbolNamesSync(args) => {
                    AppCommand::DataSymbolNamesSync(args.into())
                }
                data::DataSubcommand::Query(q) => AppCommand::DataQuery(q.into()),
                data::DataSubcommand::Bars(bars_args) => AppCommand::DataBars(bars_args.into()),
                data::DataSubcommand::Coverage(a) => AppCommand::DataCoverage(a.into()),
            },
            Commands::Task(args) => match args.command {
                task::TaskSubcommand::List(a) => AppCommand::TaskList(a.into()),
                task::TaskSubcommand::Progress(a) => AppCommand::TaskProgress(a.into()),
                task::TaskSubcommand::Cancel(a) => AppCommand::TaskCancel(a.into()),
                task::TaskSubcommand::RetryFailed(a) => AppCommand::TaskRetryFailed(a.into()),
            },
            Commands::Signal(args) => match args.command {
                signal::SignalSubcommand::Snapshot(snapshot) => {
                    AppCommand::SignalSnapshot(snapshot.into())
                }
                signal::SignalSubcommand::Evaluate(evaluate) => {
                    AppCommand::SignalEvaluate(evaluate.into())
                }
            },
            Commands::Portfolio(args) => match args.command {
                portfolio::PortfolioSubcommand::Optimize(optimize) => {
                    AppCommand::PortfolioOptimize(optimize.into())
                }
            },
            Commands::Risk(args) => match args.command {
                risk::RiskSubcommand::Check(check) => AppCommand::RiskCheck(check.into()),
            },
            Commands::Pretrade(args) => match args.command {
                pretrade::PretradeSubcommand::Check(check) => {
                    AppCommand::PretradeCheck(check.into())
                }
            },
            Commands::Execution(args) => match args.command {
                execution::ExecutionSubcommand::Plan(plan) => {
                    AppCommand::ExecutionPlan(plan.into())
                }
            },
            Commands::WalkForward(args) => AppCommand::WalkForward(args.into()),
            Commands::Monitor(args) => match args.command {
                monitor::MonitorSubcommand::HealthReport(hr) => {
                    AppCommand::MonitorHealthReport(hr.into())
                }
            },
            Commands::Config(args) => match args.command {
                config::ConfigSubcommand::Snapshot(s) => AppCommand::ConfigSnapshot(s.into()),
                config::ConfigSubcommand::List(l) => AppCommand::ConfigList(l.into()),
                config::ConfigSubcommand::Get(g) => AppCommand::ConfigGet(g.into()),
            },
        }
    }
}
