"""LangGraph StateGraph for the Albert Thought Agent FSM.
START -> p0 -> p1 -> p2 -> p3 ; p3 --[REWORK & attempt<=cap]--> p2 ; --[else]--> p4 -> p5 -> END
"""
import os
from functools import wraps
from langgraph.graph import StateGraph, START, END
from langgraph.errors import GraphInterrupt
from albert.state import AlbertState
from albert.phases.phase_0_intake_grounding import phase_0_intake_grounding
from albert.phases.phase_1_ambiguity_hunt import phase_1_ambiguity_hunt
from albert.phases.phase_2_challenge_generation import phase_2_challenge_generation
from albert.phases.phase_3_self_critique_audit import phase_3_self_critique_audit
from albert.phases.phase_4_signals_action_gate import phase_4_signals_action_gate
from albert.phases.phase_5_assemble_render import phase_5_assemble_render


def _max_rework() -> int:
    try:
        return max(0, int(os.environ.get("ALBERT_MAX_REWORK", "2")))
    except (TypeError, ValueError):
        return 2


def _route_after_audit(state: dict) -> str:
    if state.get("phase_3_verdict") == "REWORK" and state.get("phase_3_attempt_count", 0) <= _max_rework():
        return "phase_2_challenge_generation"
    return "phase_4_signals_action_gate"


def _wrap(name, fn):
    @wraps(fn)
    def w(state):
        from albert import progress as _p
        from albert.stage_summary import emit_phase_error, emit_phase_start_summary, emit_stage_summary
        emit_phase_start_summary(name, state)
        _p.phase_start(name, {"state_keys": list(state.keys())[:20]})
        try:
            result = fn(state)
            if not isinstance(result, dict):
                raise TypeError(f"{name} must return dict, got {type(result).__name__}")
            merged = dict(state); merged.update(result)
            result.update(emit_stage_summary(name, merged))
            _p.phase_end(name, {"ok": True})
            return result
        except GraphInterrupt:
            _p.emit(name, "phase_interrupt", {"reason": "interrupt"}); raise
        except Exception as e:
            emit_phase_error(name, state, e)
            _p.emit(name, "phase_error", {"error": type(e).__name__, "message": str(e)[:300]}); raise
    return w


def build_graph(checkpointer=None):
    g = StateGraph(AlbertState)
    for nm, fn in [("phase_0_intake_grounding", phase_0_intake_grounding),
                   ("phase_1_ambiguity_hunt", phase_1_ambiguity_hunt),
                   ("phase_2_challenge_generation", phase_2_challenge_generation),
                   ("phase_3_self_critique_audit", phase_3_self_critique_audit),
                   ("phase_4_signals_action_gate", phase_4_signals_action_gate),
                   ("phase_5_assemble_render", phase_5_assemble_render)]:
        g.add_node(nm, _wrap(nm, fn))
    g.add_edge(START, "phase_0_intake_grounding")
    g.add_edge("phase_0_intake_grounding", "phase_1_ambiguity_hunt")
    g.add_edge("phase_1_ambiguity_hunt", "phase_2_challenge_generation")
    g.add_edge("phase_2_challenge_generation", "phase_3_self_critique_audit")
    g.add_conditional_edges("phase_3_self_critique_audit", _route_after_audit,
        {"phase_2_challenge_generation": "phase_2_challenge_generation",
         "phase_4_signals_action_gate": "phase_4_signals_action_gate"})
    g.add_edge("phase_4_signals_action_gate", "phase_5_assemble_render")
    g.add_edge("phase_5_assemble_render", END)
    return g.compile(checkpointer=checkpointer)
