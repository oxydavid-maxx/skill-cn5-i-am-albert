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


def test_phase_0_parallel_waves_preserve_order(monkeypatch):
    # Multi-query waves now fan out via parallel_map; output ordering must match
    # the query ordering regardless of concurrency.
    import albert.phases.phase_0_intake_grounding as m
    monkeypatch.setattr(m, "call_claude", lambda **k:
        {"queries": ["q1", "q2", "q3"]} if k["purpose"] == "intake_grounding"
        else {"reframing": "r", "higher_level_question": "hq", "wave2_queries": ["q4", "q5"]})
    monkeypatch.setattr(m, "websearch", lambda q: {"query": q, "results": f"res-{q}"})
    state = {"albert_input": {"current_answer": "x", "mode": "standalone",
             "proposal": {"domain": "auto"}, "research_state": {}, "meeting_context": "BU"}}
    out = phase_0_intake_grounding(state)
    assert [r["query"] for r in out["research"]] == ["q1", "q2", "q3", "q4", "q5"]
    assert out["phase_0_status"] == "passed"
