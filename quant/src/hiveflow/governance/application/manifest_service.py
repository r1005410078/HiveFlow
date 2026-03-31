from datetime import datetime, timezone
from uuid import uuid4

from hiveflow.governance.domain.manifest import DataManifest
from hiveflow.governance.infrastructure.manifest_repo_ndjson import NdjsonManifestRepository


class ManifestService:
    def __init__(self, repo: NdjsonManifestRepository) -> None:
        self.repo = repo

    def create_manifest(
        self,
        *,
        as_of: str,
        data_source: str,
        fallback_used: bool,
        symbols_count: int,
        data_hash: str,
    ) -> DataManifest:
        now = datetime.now(timezone.utc).isoformat()
        suffix = str(uuid4())[:6]
        manifest = DataManifest(
            manifest_id=f"dm_{as_of.replace('-', '')}_{suffix}",
            run_id=f"run_{as_of.replace('-', '')}_{suffix}",
            as_of=as_of,
            data_source=data_source,
            fallback_used=fallback_used,
            symbols_count=symbols_count,
            data_hash=data_hash,
            created_at=now,
        )
        self.repo.append(manifest)
        return manifest

    def get_manifest(self, manifest_id: str) -> DataManifest:
        return self.repo.get_by_id(manifest_id)
