from albert import deliberation
from albert.phases import phase_quick_combined as pq


def test_quick_phase_populates_contract(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    monkeypatch.setattr(pq, "call_claude", lambda **k: {
        "albert_challenges": [{"bone": 2, "challenge": "c", "why_albert_would_ask": "w",
                               "severity": "high", "current_answer_strength": "weak",
                               "generator": "winning", "status": "needs_bu_judgment",
                               "evidence_refs": ["R1"]}],
        "weak_points": ["wp"], "would_survive_leadership": False,
        "top_ambiguities": [{"term": "t", "why_dangerous": "d", "precise_question": "q"},
                            {"term": "t2", "why_dangerous": "d", "precise_question": "q"},
                            {"term": "t3", "why_dangerous": "d", "precise_question": "q"}],
        "premature_end_atoms": {"open_high_impact_challenges": 2, "new_info_rate": "high"},
        "drift_atoms": {}, "proposed_next_action": "continue_research",
        "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
        "reproducible_judgment": "j", "verdict_standalone": "要補證據",
        "light": "yellow", "readiness_score_delta": 0})
    state = {"current_answer": "x", "research_state": {}, "research": [],
             "albert_input": {"current_answer": "x", "mode": "standalone"}}
    out = pq.phase_quick_combined(state)
    assert out["albert_challenges"][0]["bone"] == 2
    assert out["verdict_standalone"] == "要補證據"
    assert out["premature_end_risk"]["level"] in ("low", "medium", "high")
    assert out["recommended_next_action"]
    assert out["verdict"] == "exhausted"
    assert out["phase_4_status"] == "passed"
    assert deliberation.emitted("phase_quick_combined")


def test_quick_phase_degraded_on_failure(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    def boom(**k): raise RuntimeError("llm down")
    monkeypatch.setattr(pq, "call_claude", boom)
    state = {"current_answer": "x", "research_state": {}, "research": [],
             "albert_input": {"current_answer": "x", "mode": "standalone"}}
    out = pq.phase_quick_combined(state)
    assert out["phase_4_status"] == "failed"
    assert deliberation.emitted("phase_quick_combined")
