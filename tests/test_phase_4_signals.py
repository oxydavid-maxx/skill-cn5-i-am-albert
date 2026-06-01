# tests/test_phase_4_signals.py
from albert.phases.phase_4_signals_action_gate import phase_4_signals_action_gate

def _resp(action="synthesize"):
    return {"premature_end_atoms": {"open_high_impact_challenges": 2, "new_info_rate": "high",
            "challenge_map_mostly_classified": False, "unresolved_are_human_data_decision_only": False,
            "meta_question_search_found_new_high_impact_angle": True},
            "drift_atoms": {"current_focus_in_original_high_value_set": True, "high_value_branch_ignored": False},
            "recommended_next_probe": [{"probe": "p", "why": "w", "impact": "high", "answerability": "low"}],
            "missing_evidence": [{"item": "x", "who_can_answer": "public"}],
            "questions_albert_would_ask": ["q?"], "proposed_next_action": action, "rationale": "r",
            "decision_gate": {"can_decide_now": [], "cannot_decide": ["price"], "owners": []},
            "reproducible_judgment": "rj"}

def test_level_from_atoms_and_action_vetoed(monkeypatch):
    import albert.phases.phase_4_signals_action_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp("synthesize"))
    out = phase_4_signals_action_gate({"current_answer": "x", "albert_challenges": [],
        "research_state": {"new_info_rate": "high"}})
    assert out["premature_end_risk"]["level"] == "high"
    assert out["premature_end_risk"]["grounded_in"] == "research_state"
    assert out["recommended_next_action"] == "continue_research"   # synthesize vetoed by high premature_end
    assert out["recommended_next_probe"][0]["priority"] == 1
    assert out["phase_4_status"] == "passed"

def test_inferred_when_no_telemetry(monkeypatch):
    import albert.phases.phase_4_signals_action_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp("branch"))
    out = phase_4_signals_action_gate({"current_answer": "x", "albert_challenges": [], "research_state": {}})
    assert out["premature_end_risk"]["grounded_in"] == "inferred"
    assert out["premature_end_risk"]["low_confidence"] is True
