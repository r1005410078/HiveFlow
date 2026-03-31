pub mod data;
pub mod pipeline;

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
    Pipeline(pipeline::PipelineArgs),
    Data(data::DataArgs),
}
