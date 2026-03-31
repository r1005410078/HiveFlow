from application.contracts.cli_output import ok_output


def test_ok_output_required_fields():
    """验证 CLI 标准成功响应包含所有必填字段。"""
    payload = ok_output(command="hf pipeline daily", run_id="run_1", data={"as_of": "2026-04-01"})
    for key in ["schema_version", "command", "run_id", "status", "generated_at", "data", "warnings", "errors"]:
        assert key in payload
    assert payload["status"] == "ok"
    assert payload["warnings"] == []
    assert payload["errors"] == []
    assert payload["source"] == "system"
    assert payload["advice_only"] is False
