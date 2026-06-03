from albert import deliberation
from albert.phases import phase_flash as pf


def _stub_res():
    return {"albert_challenges": [{"bone": 2, "challenge": "c", "why_albert_would_ask": "w",
            "severity": "high", "current_answer_strength": "weak", "generator": "winning",
            "status": "needs_bu_judgment"}],
            "weak_points": ["wp"], "would_survive_leadership": False,
            "top_ambiguities": [{"term": "t", "why_dangerous": "d", "precise_question": "q"},
                                {"term": "t2", "why_dangerous": "d", "precise_question": "q"},
                                {"term": "t3", "why_dangerous": "d", "precise_question": "q"}],
            "premature_end_atoms": {"open_high_impact_challenges": 2, "new_info_rate": "high"},
            "drift_atoms": {}, "proposed_next_action": "continue_research",
            "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
            "reproducible_judgment": "j", "verdict_standalone": "要補證據",
            "light": "yellow", "readiness_score_delta": 0}


def test_flash_populates_contract_from_albert_input(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    monkeypatch.setattr(pf, "call_claude", lambda **k: _stub_res())
    state = {"albert_input": {"current_answer": "MY PROPOSAL TEXT", "mode": "standalone",
                              "output_purpose": "meeting_defense", "proposal": {"title": "P"}}}
    out = pf.phase_flash(state)
    assert out["current_answer"] == "MY PROPOSAL TEXT"
    assert out["research"] == []
    assert out["verdict_standalone"] == "要補證據"
    assert out["verdict"] == "exhausted"
    assert out["phase_4_status"] == "passed"
    md = (tmp_path / "deliberation.md").read_text(encoding="utf-8")
    assert "PHASE F ─ 閃電審查" in md
    assert "PHASE 0 ─ 研究" not in md


def test_flash_degraded_on_failure(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    def boom(**k): raise RuntimeError("down")
    monkeypatch.setattr(pf, "call_claude", boom)
    state = {"albert_input": {"current_answer": "x", "mode": "standalone"}}
    out = pf.phase_flash(state)
    assert out["phase_4_status"] == "failed"
    assert deliberation.emitted("phase_flash")
