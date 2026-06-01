# tests/test_phase_0_intake.py
from albert.phases.phase_0_intake_grounding import phase_0_intake_grounding

def test_phase_0_grounds_and_reflects(monkeypatch):
    import albert.phases.phase_0_intake_grounding as m
    monkeypatch.setattr(m, "call_claude", lambda **k:
        {"queries": ["q1"]} if k["purpose"] == "intake_grounding"
        else {"reframing": "r", "higher_level_question": "hq", "wave2_queries": ["q2"]})
    monkeypatch.setattr(m, "websearch", lambda q: {"query": q, "results": "SOTA moved compute to zone"})
    state = {"albert_input": {"current_answer": "zonal controller, no spec", "mode": "standalone",
             "proposal": {"domain": "auto"}, "research_state": {}, "meeting_context": "BU review"}}
    out = phase_0_intake_grounding(state)
    assert out["phase_0_complete"] and out["current_answer"]
    assert out["meta_question"]["higher_level_question"] == "hq"
    assert isinstance(out["research"], list) and out["research"]
