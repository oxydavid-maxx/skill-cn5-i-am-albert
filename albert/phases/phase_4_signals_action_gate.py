"""Phase 4 (bones 7,9,12): LLM produces atoms + a proposed action; signals.py computes the
risk levels and vetoes an inconsistent action."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert.signals_apply import apply_signals
from albert import deliberation

_STUB = {"premature_end_atoms": {"open_high_impact_challenges": 1, "new_info_rate": "unknown",
         "challenge_map_mostly_classified": False, "unresolved_are_human_data_decision_only": False,
         "meta_question_search_found_new_high_impact_angle": False},
         "drift_atoms": {}, "recommended_next_probe": [], "missing_evidence": [],
         "questions_albert_would_ask": [], "proposed_next_action": "continue_research", "rationale": "(LLM unavailable)",
         "decision_gate": {"can_decide_now": [], "cannot_decide": ["(LLM unavailable)"], "owners": []},
         "reproducible_judgment": "",
         "verdict_standalone": "產品定義不完整", "light": "red", "readiness_score_delta": -2}


def phase_4_signals_action_gate(state: dict) -> dict:
    rs = state.get("research_state") or {}
    ctx = (f"Current answer:\n{state.get('current_answer','')[:3000]}\n\n"
           f"Challenges:\n{json.dumps(state.get('albert_challenges', []), ensure_ascii=False)[:10000]}\n\n"
           f"research_state:\n{json.dumps(rs, ensure_ascii=False)[:3000]}\n"
           f"readiness_scores:\n{json.dumps(state.get('readiness_scores', {}), ensure_ascii=False)[:1000]}\n")
    status = "passed"
    try:
        res = call_claude(model=model_for_role("signals_action_gate"),
                          system=load_prompt("signals_action_gate"), user=ctx,
                          json_schema=schemas.SIGNALS_VERDICT_MERGED, purpose="signals_action_gate")
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_4 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = dict(_STUB), "failed"

    apply_signals(state, res)
    state["phase_4_status"], state["phase_4_complete"] = status, True
    deliberation.block("phase_4_signals_action_gate", "Phase 4 — Signals & action gate",
                       deliberation.render_signals({
                           "premature_end_risk": state["premature_end_risk"],
                           "research_drift_risk": state["research_drift_risk"],
                           "proposed_next_action": res.get("proposed_next_action", "continue_research"),
                           "recommended_next_action": state["recommended_next_action"],
                       }))
    return state
