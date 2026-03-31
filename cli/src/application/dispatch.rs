use crate::application::handlers::pipeline_daily;
use crate::cmd::{Cli, Commands};
use crate::error::AppError;

pub fn run(cli: Cli) -> Result<(), AppError> {
    match cli.command {
        Commands::Pipeline(args) => pipeline_daily::handle(args),
        Commands::Data(_) => {
            // 预留命令，当前返回成功并打印最小提示。
            println!("{}", "{\"status\":\"ok\",\"message\":\"data command placeholder\"}");
            Ok(())
        }
    }
}
