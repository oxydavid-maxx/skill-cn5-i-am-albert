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


def test_phase_4_emits_verdict_fields(monkeypatch):
    import albert.phases.phase_4_signals_action_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {
        "premature_end_atoms": {"open_high_impact_challenges": 0, "new_info_rate": "low"},
        "drift_atoms": {}, "recommended_next_probe": [], "missing_evidence": [],
        "questions_albert_would_ask": [], "proposed_next_action": "pull_human", "rationale": "r",
        "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
        "reproducible_judgment": "rj",
        "verdict_standalone": "要補證據", "light": "yellow", "readiness_score_delta": -1})
    out = m.phase_4_signals_action_gate({"current_answer": "x", "albert_challenges": [], "research_state": {}})
    assert out["verdict_standalone"] == "要補證據"
    assert out["light"] == "yellow"
    assert out["readiness_score_delta"] == -1
    assert out["recommended_next_action"]  # signals.py still vetoes/sets it


def test_phase_4_stub_fallback_sets_verdict_fields(monkeypatch):
    import albert.phases.phase_4_signals_action_gate as m
    def _boom(**k):
        raise RuntimeError("LLM unavailable")
    monkeypatch.setattr(m, "call_claude", _boom)
    out = m.phase_4_signals_action_gate({"current_answer": "x", "albert_challenges": [], "research_state": {}})
    assert out["phase_4_status"] == "failed"
    assert out["verdict_standalone"] == "產品定義不完整"
    assert out["light"] == "red"
    assert out["readiness_score_delta"] == -2
