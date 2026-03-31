def run_risk_gate(weights: list[dict], max_single_weight: float = 0.3) -> dict:
    violations = [w for w in weights if w["target_weight"] > max_single_weight]
    if violations:
        return {"gate_result": "block", "block_reason": "SINGLE_WEIGHT_EXCEEDED", "evidence_snapshot": violations}
    return {"gate_result": "pass", "block_reason": None, "evidence_snapshot": []}
