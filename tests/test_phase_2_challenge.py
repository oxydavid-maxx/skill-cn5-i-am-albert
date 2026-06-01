# tests/test_phase_2_challenge.py
from albert.phases.phase_2_challenge_generation import phase_2_challenge_generation

def _resp():
    return {"albert_challenges": [{"challenge": "why win?", "why_albert_would_ask": "parity",
            "status": "needs_bu_judgment", "severity": "high", "current_answer_strength": "weak",
            "generator": "winning", "bone": 2, "high_impact": True}],
        "weak_points": ["no ROI number"], "missing_business_context": ["TAM"], "would_survive_leadership": False}

def test_generates(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp())
    out = phase_2_challenge_generation({"current_answer": "x", "research": [], "top_ambiguities": [],
        "meta_question": {}, "skeptic_output": [], "source_critic_output": [], "output_purpose": "meeting_defense"})
    assert out["albert_challenges"][0]["severity"] == "high"
    assert out["weak_points"] == ["no ROI number"]
    assert out["would_survive_leadership"] is False and out["phase_2_status"] == "passed"

def test_rework_feedback(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    cap = {}
    monkeypatch.setattr(m, "call_claude", lambda **k: (cap.__setitem__("u", k["user"]), _resp())[1])
    phase_2_challenge_generation({"current_answer": "x", "research": [], "top_ambiguities": [],
        "meta_question": {}, "skeptic_output": [], "source_critic_output": [], "output_purpose": "x",
        "phase_3_rounds": [{"weaknesses": [{"classification": "addressable", "issue": "v", "suggested_sharpening": "tie to roadmap"}]}]})
    assert "tie to roadmap" in cap["u"]

def test_stub(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = phase_2_challenge_generation({"current_answer": "x", "research": [], "top_ambiguities": [],
        "meta_question": {}, "skeptic_output": [], "source_critic_output": [], "output_purpose": "x"})
    assert out["phase_2_status"] == "failed" and out["albert_challenges"]
