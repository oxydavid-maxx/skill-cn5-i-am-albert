from albert.signals_apply import apply_signals


def test_apply_signals_sets_risk_action_verdict():
    state = {"research_state": {}}
    res = {"premature_end_atoms": {"open_high_impact_challenges": 3, "new_info_rate": "high"},
           "drift_atoms": {}, "proposed_next_action": "synthesize",
           "reproducible_judgment": "建議 synthesize。",
           "verdict_standalone": "要補證據", "light": "yellow", "readiness_score_delta": 0,
           "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []}}
    apply_signals(state, res)
    assert state["premature_end_risk"]["level"] == "high"
    assert state["premature_end_risk"]["why"]
    assert state["recommended_next_action"] == "continue_research"
    assert "經訊號否決改為 continue_research" in state["reproducible_judgment"]
    assert state["verdict_standalone"] == "要補證據"
    assert state["light"] == "yellow"
