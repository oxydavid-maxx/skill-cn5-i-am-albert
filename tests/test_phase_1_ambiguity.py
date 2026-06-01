# tests/test_phase_1_ambiguity.py
from albert.phases.phase_1_ambiguity_hunt import phase_1_ambiguity_hunt
def _a(t): return {"term": t, "why_dangerous": "w", "precise_question": "p"}
def test_three(monkeypatch):
    import albert.phases.phase_1_ambiguity_hunt as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"top_ambiguities": [_a("a"), _a("b"), _a("c")]})
    out = phase_1_ambiguity_hunt({"current_answer": "no spec", "research": []})
    assert len(out["top_ambiguities"]) == 3 and out["phase_1_status"] == "passed"
def test_stub(monkeypatch):
    import albert.phases.phase_1_ambiguity_hunt as m
    monkeypatch.setattr(m, "call_claude", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = phase_1_ambiguity_hunt({"current_answer": "x", "research": []})
    assert len(out["top_ambiguities"]) == 3 and out["phase_1_status"] == "failed"
