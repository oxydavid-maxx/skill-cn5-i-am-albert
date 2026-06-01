# tests/test_phase_0_intake.py
from albert.phases.phase_0_intake_grounding import phase_0_intake_grounding


def test_phase_0_single_wave_default(monkeypatch):
    # Default (ALBERT_RESEARCH_REFLECT unset): exactly ONE LLM call (intake),
    # no search_reflection round-trip, all queries searched in one parallel wave.
    monkeypatch.delenv("ALBERT_RESEARCH_REFLECT", raising=False)
    import albert.phases.phase_0_intake_grounding as m
    purposes = []

    def fake_call(**k):
        purposes.append(k["purpose"])
        return {"queries": ["q1", "q2", "q3"], "meta_question": "what would a mature SOTA product do"}

    workers_seen = {}

    def fake_parallel_map(fn, items, max_workers=6):
        items = list(items)
        workers_seen["mw"] = max_workers
        return [fn(x) for x in items]

    monkeypatch.setattr(m, "call_claude", fake_call)
    monkeypatch.setattr(m, "parallel_map", fake_parallel_map)
    monkeypatch.setattr(m, "websearch", lambda q: {"query": q, "results": f"res-{q}"})
    state = {"albert_input": {"current_answer": "zonal controller, no spec", "mode": "standalone",
             "proposal": {"domain": "auto"}, "research_state": {}, "meeting_context": "BU review"}}
    out = phase_0_intake_grounding(state)

    # Only the intake call — no separate search_reflection call.
    assert purposes == ["intake_grounding"]
    assert "search_reflection" not in purposes
    # All queries searched in a single concurrent wave; ordering preserved.
    assert [r["query"] for r in out["research"]] == ["q1", "q2", "q3"]
    # max_workers covers all queries so the wave starts together (>= len, >= 6).
    assert workers_seen["mw"] >= 6 and workers_seen["mw"] >= 3
    # meta_question populated from the intake plan's meta framing.
    assert out["meta_question"]["higher_level_question"] == "what would a mature SOTA product do"
    assert out["phase_0_complete"] and out["current_answer"]
    assert out["phase_0_status"] == "passed"


def test_phase_0_meta_question_empty_when_absent(monkeypatch):
    # If the intake plan omits a meta framing field, meta_question is {} (Phase 2 tolerates).
    monkeypatch.delenv("ALBERT_RESEARCH_REFLECT", raising=False)
    import albert.phases.phase_0_intake_grounding as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"queries": ["q1"]})
    monkeypatch.setattr(m, "websearch", lambda q: {"query": q, "results": "r"})
    state = {"albert_input": {"current_answer": "x", "mode": "standalone",
             "proposal": {"domain": "auto"}, "research_state": {}, "meeting_context": "BU"}}
    out = phase_0_intake_grounding(state)
    assert out["meta_question"] == {}
    assert out["phase_0_complete"]


def test_phase_0_reflect_env_honored(monkeypatch):
    # ALBERT_RESEARCH_REFLECT=1 retains the old two-wave + reflection path.
    monkeypatch.setenv("ALBERT_RESEARCH_REFLECT", "1")
    import albert.phases.phase_0_intake_grounding as m
    purposes = []

    def fake_call(**k):
        purposes.append(k["purpose"])
        if k["purpose"] == "intake_grounding":
            return {"queries": ["q1"]}
        return {"reframing": "r", "higher_level_question": "hq", "wave2_queries": ["q2"]}

    monkeypatch.setattr(m, "call_claude", fake_call)
    monkeypatch.setattr(m, "websearch", lambda q: {"query": q, "results": "SOTA moved compute to zone"})
    state = {"albert_input": {"current_answer": "zonal controller, no spec", "mode": "standalone",
             "proposal": {"domain": "auto"}, "research_state": {}, "meeting_context": "BU review"}}
    out = phase_0_intake_grounding(state)
    # Old path: reflection call fired.
    assert "search_reflection" in purposes
    assert out["meta_question"]["higher_level_question"] == "hq"
    assert [r["query"] for r in out["research"]] == ["q1", "q2"]
    assert out["phase_0_complete"] and out["current_answer"]
    assert out["phase_0_status"] == "passed"
