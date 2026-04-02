mod application;
mod cmd;
mod contracts;
mod domain;
mod error;
mod infrastructure;

use crate::cmd::Cli;
use clap::Parser;

fn main() {
    let command = Cli::parse();
    if let Err(err) = application::dispatch::run(command.into()) {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
