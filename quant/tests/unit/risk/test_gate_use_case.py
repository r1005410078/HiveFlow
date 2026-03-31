from hiveflow.risk.application.gate_use_case import run_risk_gate


def test_risk_gate_block_overweight():
    """验证 L5 对超限权重触发 block。"""
    r = run_risk_gate([{"symbol": "000001.SZ", "target_weight": 0.4}], max_single_weight=0.3)
    assert r["gate_result"] == "block"
