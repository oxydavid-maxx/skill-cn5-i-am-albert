# tests/test_self_critique_loop.py
import tempfile
import threading
from albert.graph import build_graph

def test_loop_terminates(monkeypatch):
    import albert.phases.phase_0_intake_grounding as p0, albert.phases.phase_1_ambiguity_hunt as p1
    import albert.phases.phase_2_challenge_generation as p2, albert.phases.phase_3_self_critique_audit as p3
    import albert.phases.phase_4_signals_action_gate as p4, albert.phases.phase_5_assemble_render as p5
    monkeypatch.setenv("ALBERT_MAX_REWORK", "2")
    monkeypatch.setattr(p0, "call_claude", lambda **k: {"queries": []} if k["purpose"]=="intake_grounding" else {"higher_level_question":"h","wave2_queries":[]})
    monkeypatch.setattr(p0, "websearch", lambda q: {"query": q, "results": ""})
    monkeypatch.setattr(p1, "call_claude", lambda **k: {"top_ambiguities":[{"term":"t","why_dangerous":"w","precise_question":"p"}]*3})
    monkeypatch.setattr(p2, "call_claude", lambda **k: {"albert_challenges":[{"challenge":"x","why_albert_would_ask":"y","status":"blocked","severity":"high","current_answer_strength":"weak","generator":"winning","bone":2}],"weak_points":[],"missing_business_context":[],"would_survive_leadership":False})
    # Phase 3 votes are now independent parallel call_claude calls. Each phase-3
    # attempt fans out exactly 3 votes and blocks until all 3 finish before the
    # next attempt starts, so the block-of-3 attempt derivation still holds; just
    # guard the shared counter for thread-safety.
    calls = {"n": 0, "lock": threading.Lock()}
    def _fake_vote(**k):
        # 3 addressable votes on attempts 1-2 (rework), all-residual on attempt 3 (exhausted)
        with calls["lock"]:
            calls["n"] += 1
            attempt = (calls["n"] - 1) // 3 + 1
        cls = "addressable" if attempt < 3 else "residual"
        return {"round": attempt, "weaknesses": [{"classification": cls, "issue": "i"}], "verdict": "rework" if attempt<3 else "exhausted"}
    monkeypatch.setattr(p3, "call_claude", _fake_vote)
    monkeypatch.setattr(p4, "call_claude", lambda **k: {"premature_end_atoms":{"open_high_impact_challenges":0,"new_info_rate":"low"},"drift_atoms":{},"recommended_next_probe":[],"missing_evidence":[],"questions_albert_would_ask":[],"proposed_next_action":"synthesize","rationale":"r","decision_gate":{"can_decide_now":[],"cannot_decide":[],"owners":[]},"reproducible_judgment":"rj"})
    monkeypatch.setattr(p5, "call_claude", lambda **k: {"verdict_standalone":"可推進","light":"green","readiness_score_delta":1})
    monkeypatch.setattr(p5, "send_email", lambda **k: "skipped")
    g = build_graph()
    state = {"albert_input": {"current_answer": "a", "mode": "standalone", "proposal": {}, "research_state": {}}, "run_dir": tempfile.mkdtemp(), "run_id": "r", "mode": "standalone"}
    final = g.invoke(state, config={"configurable": {"thread_id": "t", "recursion_limit": 100}})
    assert final["phase_5_complete"] is True and final["phase_3_attempt_count"] == 3
