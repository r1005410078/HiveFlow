from domain.errors import ErrorCode


def test_required_error_codes_exist():
    """验证错误码枚举覆盖 MVP 关键失败场景。"""
    required = {"DATA_FETCH_FAILED", "LOW_COVERAGE", "SOLVER_FALLBACK", "RISK_GATE_BLOCKED", "EXECUTION_PRECHECK_FAILED"}
    assert required.issubset({e.value for e in ErrorCode})
