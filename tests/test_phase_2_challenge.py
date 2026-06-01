# tests/test_phase_2_challenge.py
from albert.phases.phase_2_challenge_generation import phase_2_challenge_generation
from albert.state import GENERATORS

def _resp():
    return {"albert_challenges": [{"challenge": "why win?", "why_albert_would_ask": "parity",
            "status": "needs_bu_judgment", "severity": "high", "current_answer_strength": "weak",
            "generator": "winning", "bone": 2, "high_impact": True}],
        "weak_points": ["no ROI number"], "missing_business_context": ["TAM"], "would_survive_leadership": False}

def _base_state(**extra):
    s = {"current_answer": "x", "research": [], "top_ambiguities": [],
         "meta_question": {}, "skeptic_output": [], "source_critic_output": [],
         "output_purpose": "meeting_defense"}
    s.update(extra)
    return s

def test_fans_out_per_generator_and_merges(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    calls = {"n": 0}
    def fake(**k):
        calls["n"] += 1
        return _resp()
    monkeypatch.setattr(m, "call_claude", fake)
    out = phase_2_challenge_generation(_base_state())
    # one call per generator
    assert calls["n"] == len(GENERATORS) == 6
    # merge concatenates all 6 slices' challenges / weak_points / missing_business_context
    assert len(out["albert_challenges"]) == 6
    assert len(out["weak_points"]) == 6
    assert len(out["missing_business_context"]) == 6
    assert out["albert_challenges"][0]["severity"] == "high"
    assert out["phase_2_status"] == "passed"

def _generator_of(user):
    # The per-generator FOCUS line names exactly one generator.
    for g in GENERATORS:
        if f"'{g}' generator" in user:
            return g
    return None

def test_and_fold_would_survive_leadership(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    # convergence_redteam votes False; everyone else True -> overall False.
    def fake(**k):
        r = _resp()
        r["would_survive_leadership"] = _generator_of(k["user"]) != "convergence_redteam"
        return r
    monkeypatch.setattr(m, "call_claude", fake)
    out = phase_2_challenge_generation(_base_state())
    assert out["would_survive_leadership"] is False

def test_and_fold_all_true(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    def fake(**k):
        r = _resp()
        r["would_survive_leadership"] = True
        return r
    monkeypatch.setattr(m, "call_claude", fake)
    out = phase_2_challenge_generation(_base_state())
    assert out["would_survive_leadership"] is True

def test_all_fail_status_failed(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = phase_2_challenge_generation(_base_state())
    assert out["phase_2_status"] == "failed" and out["albert_challenges"]

def test_partial_fail_proceeds(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    def fake(**k):
        if _generator_of(k["user"]) == "timing":  # one generator down
            raise RuntimeError("one generator down")
        return _resp()
    monkeypatch.setattr(m, "call_claude", fake)
    out = phase_2_challenge_generation(_base_state())
    # not all failed -> passed; 5 real slices merged
    assert out["phase_2_status"] == "passed"
    assert len(out["albert_challenges"]) == 5

def test_rework_feedback_reaches_each_generator(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    caps = []
    def fake(**k):
        caps.append(k["user"])
        return _resp()
    monkeypatch.setattr(m, "call_claude", fake)
    phase_2_challenge_generation(_base_state(
        output_purpose="x",
        phase_3_rounds=[{"weaknesses": [{"classification": "addressable", "issue": "v",
                         "suggested_sharpening": "tie to roadmap"}]}]))
    assert len(caps) == 6
    assert all("tie to roadmap" in u for u in caps)

def test_focus_line_per_generator(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    caps = []
    monkeypatch.setattr(m, "call_claude", lambda **k: (caps.append(k["user"]), _resp())[1])
    phase_2_challenge_generation(_base_state())
    joined = "\n".join(caps)
    for g in GENERATORS:
        assert g in joined
