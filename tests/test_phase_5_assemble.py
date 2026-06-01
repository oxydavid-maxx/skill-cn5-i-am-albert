# tests/test_phase_5_assemble.py
from albert.phases.phase_5_assemble_render import phase_5_assemble_render

def _state(tmp_path, statuses, verdict="exhausted",
           verdict_standalone="可推進", light="green", readiness_score_delta=1):
    s = {"run_dir": str(tmp_path), "run_id": "r", "mode": "standalone", "proposal": {"title": "T"},
         "current_answer": "a", "top_ambiguities": [], "albert_challenges": [], "weak_points": [],
         "missing_business_context": [], "missing_evidence": [], "questions_albert_would_ask": [],
         "recommended_next_probe": [], "recommended_next_action": "synthesize", "rationale": "r",
         "premature_end_risk": {"level": "low", "grounded_in": "inferred"},
         "research_drift_risk": {"level": "low", "grounded_in": "inferred"},
         "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
         "reproducible_judgment": "rj", "phase_3_verdict": "EXHAUSTED",
         # Seeded by phase 4 (Task 1): phase 5 reads these, makes no LLM call.
         "verdict_standalone": verdict_standalone, "light": light,
         "readiness_score_delta": readiness_score_delta}
    s.update(statuses); return s

def test_phase_5_makes_no_llm_call(tmp_path, monkeypatch):
    import albert.phases.phase_5_assemble_render as m
    def _boom(**k):
        raise AssertionError("phase 5 must not call_claude")
    monkeypatch.setattr(m, "call_claude", _boom, raising=False)
    monkeypatch.setattr(m, "send_email", lambda **k: "skipped")
    out = phase_5_assemble_render(_state(tmp_path, {f"phase_{i}_status": "passed" for i in range(5)}))
    assert out["phase_5_complete"] is True

def test_passed_sets_verdict_and_not_degraded(tmp_path, monkeypatch):
    import albert.phases.phase_5_assemble_render as m
    monkeypatch.setattr(m, "send_email", lambda **k: "skipped")
    out = phase_5_assemble_render(_state(tmp_path, {f"phase_{i}_status": "passed" for i in range(5)}))
    assert out["degraded"] is False and out["verdict"] in ("continue", "exhausted", "rework")
    assert out["light"] == "green" and out["challenge_json_path"] and out["report_path"]

def test_failed_phase_degrades_and_downgrades_green(tmp_path, monkeypatch):
    import albert.phases.phase_5_assemble_render as m
    monkeypatch.setattr(m, "send_email", lambda **k: "skipped")
    out = phase_5_assemble_render(_state(tmp_path, {"phase_0_status": "passed", "phase_1_status": "failed",
        "phase_2_status": "passed", "phase_3_status": "passed", "phase_4_status": "passed"},
        verdict_standalone="可推進", light="green", readiness_score_delta=2))
    assert out["degraded"] is True and out["light"] != "green"
