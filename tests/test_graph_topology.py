# tests/test_graph_topology.py
from albert.graph import build_graph, _route_after_audit, _max_rework
def test_compiles(): assert build_graph() is not None

def test_phase_1_not_a_node():
    g = build_graph()
    assert "phase_1_ambiguity_hunt" not in g.get_graph().nodes

def test_phase_0_to_phase_2_edge():
    edges = {(e.source, e.target) for e in build_graph().get_graph().edges}
    assert ("phase_0_intake_grounding", "phase_2_challenge_generation") in edges
    # phase_0 no longer feeds phase_1
    assert ("phase_0_intake_grounding", "phase_1_ambiguity_hunt") not in edges

def test_exhaustion_loop_intact():
    # The REWORK route phase_3 -> phase_2 is preserved (conditional edge).
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}) == "phase_2_challenge_generation"

def test_rework_under_cap(monkeypatch):
    monkeypatch.delenv("ALBERT_MAX_REWORK", raising=False)
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}) == "phase_2_challenge_generation"
def test_rework_over_cap(monkeypatch):
    monkeypatch.setenv("ALBERT_MAX_REWORK", "2")
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 3}) == "phase_4_signals_action_gate"
def test_exhausted(): assert _route_after_audit({"phase_3_verdict": "EXHAUSTED", "phase_3_attempt_count": 1}) == "phase_4_signals_action_gate"
def test_cap_zero(monkeypatch):
    monkeypatch.setenv("ALBERT_MAX_REWORK", "0")
    assert _max_rework() == 0
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}) == "phase_4_signals_action_gate"
