#[derive(Debug, Clone)]
pub enum DomainCommand {
    PipelineDaily { as_of: String },
    DataSnapshot,
}
