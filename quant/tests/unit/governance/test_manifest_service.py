from hiveflow.governance.application.manifest_service import ManifestService
from hiveflow.governance.infrastructure.manifest_repo_ndjson import NdjsonManifestRepository


def test_create_and_get_manifest(tmp_path):
    """验证 manifest 可 append-only 写入并按 id 读取。"""
    repo = NdjsonManifestRepository(tmp_path / "data" / "manifests" / "data_manifest.ndjson")
    svc = ManifestService(repo)
    m = svc.create_manifest(
        as_of="2026-04-01",
        data_source="tengxun_shuge",
        fallback_used=False,
        symbols_count=10,
        data_hash="abc",
    )
    loaded = svc.get_manifest(m.manifest_id)
    assert loaded.manifest_id == m.manifest_id
