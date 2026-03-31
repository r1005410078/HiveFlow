mod application;
mod cmd;
mod contracts;
mod domain;
mod error;
mod infrastructure;

use crate::cmd::Cli;
use clap::Parser;

fn main() {
    let cli = Cli::parse();
    if let Err(err) = application::dispatch::run(cli) {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
