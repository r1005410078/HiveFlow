from dataclasses import dataclass


@dataclass(frozen=True)
class DataManifest:
    manifest_id: str
    run_id: str
    as_of: str
    data_source: str
    fallback_used: bool
    symbols_count: int
    data_hash: str
    created_at: str
