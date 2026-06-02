"""Phase 4 (bones 7,9,12): LLM produces atoms + a proposed action; signals.py computes the
risk levels and vetoes an inconsistent action."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert.signals import (premature_end_level, drift_level, rank_next_probe,
                            build_risk, enforce_action_consistency,
                            premature_end_why, drift_why)
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

    pe_atoms = res.get("premature_end_atoms") or _STUB["premature_end_atoms"]
    dr_atoms = res.get("drift_atoms") or {}
    pe_level, dr_level = premature_end_level(pe_atoms), drift_level(dr_atoms)
    state["premature_end_risk"] = build_risk(pe_level, pe_atoms, rs, why=premature_end_why(pe_atoms))
    state["research_drift_risk"] = build_risk(dr_level, dr_atoms, rs, why=drift_why(dr_atoms))
    state["recommended_next_probe"] = rank_next_probe(res.get("recommended_next_probe") or [])
    state["missing_evidence"] = res.get("missing_evidence") or []
    state["questions_albert_would_ask"] = res.get("questions_albert_would_ask") or []
    state["recommended_next_action"] = enforce_action_consistency(
        res.get("proposed_next_action", "continue_research"), pe_level, dr_level, state["missing_evidence"])
    state["rationale"] = res.get("rationale") or ""
    state["decision_gate"] = res.get("decision_gate") or dict(_STUB["decision_gate"])
    state["reproducible_judgment"] = res.get("reproducible_judgment") or ""
    # Verdict-presentation fields (formerly phase 5's separate LLM call). Levels
    # + action still come from signals.py above; these are presentation atoms only.
    state["verdict_standalone"] = res.get("verdict_standalone", "要補證據")
    state["light"] = res.get("light", "yellow")
    state["readiness_score_delta"] = int(res.get("readiness_score_delta", 0))
    state["phase_4_status"], state["phase_4_complete"] = status, True
    deliberation.block("phase_4_signals_action_gate", "Phase 4 — Signals & action gate",
                       deliberation.render_signals({
                           "premature_end_risk": state["premature_end_risk"],
                           "research_drift_risk": state["research_drift_risk"],
                           "proposed_next_action": res.get("proposed_next_action", "continue_research"),
                           "recommended_next_action": state["recommended_next_action"],
                       }))
    return state
