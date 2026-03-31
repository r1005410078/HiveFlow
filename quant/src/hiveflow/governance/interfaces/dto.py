from dataclasses import asdict

from hiveflow.governance.domain.manifest import DataManifest


def manifest_to_dict(manifest: DataManifest) -> dict:
    return asdict(manifest)
