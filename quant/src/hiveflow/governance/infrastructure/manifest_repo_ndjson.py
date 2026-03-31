import json
from pathlib import Path

from hiveflow.governance.domain.manifest import DataManifest
from hiveflow.governance.interfaces.dto import manifest_to_dict


class NdjsonManifestRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, manifest: DataManifest) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(manifest_to_dict(manifest), ensure_ascii=False) + "\n")

    def get_by_id(self, manifest_id: str) -> DataManifest:
        if not self.path.exists():
            raise KeyError(manifest_id)

        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                if item.get("manifest_id") == manifest_id:
                    return DataManifest(
                        manifest_id=item["manifest_id"],
                        run_id=item["run_id"],
                        as_of=item["as_of"],
                        data_source=item["data_source"],
                        fallback_used=item["fallback_used"],
                        symbols_count=item["symbols_count"],
                        data_hash=item["data_hash"],
                        created_at=item["created_at"],
                    )

        raise KeyError(manifest_id)
