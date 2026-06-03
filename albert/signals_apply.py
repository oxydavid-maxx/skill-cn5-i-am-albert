"""Deterministic signals/verdict application shared by phase_4 and phase_quick_combined.

Given an LLM result dict (atoms + proposed action + verdict-presentation fields),
compute the rule-grounded risk levels + vetoed action and write them into state.
No LLM call. Mirrors the contract phase_4 established."""
from __future__ import annotations

from albert.signals import (premature_end_level, drift_level, rank_next_probe,
                            build_risk, enforce_action_consistency,
                            premature_end_why, drift_why)

_STUB_PE = {"open_high_impact_challenges": 1, "new_info_rate": "unknown",
            "challenge_map_mostly_classified": False,
            "unresolved_are_human_data_decision_only": False,
            "meta_question_search_found_new_high_impact_angle": False}
_STUB_GATE = {"can_decide_now": [], "cannot_decide": [], "owners": []}


def apply_signals(state: dict, res: dict) -> None:
    rs = state.get("research_state") or {}
    pe_atoms = res.get("premature_end_atoms") or dict(_STUB_PE)
    dr_atoms = res.get("drift_atoms") or {}
    pe_level, dr_level = premature_end_level(pe_atoms), drift_level(dr_atoms)
    state["premature_end_risk"] = build_risk(pe_level, pe_atoms, rs, why=premature_end_why(pe_atoms))
    state["research_drift_risk"] = build_risk(dr_level, dr_atoms, rs, why=drift_why(dr_atoms))
    state["recommended_next_probe"] = rank_next_probe(res.get("recommended_next_probe") or [])
    state["missing_evidence"] = res.get("missing_evidence") or []
    state["questions_albert_would_ask"] = res.get("questions_albert_would_ask") or []
    _proposed = res.get("proposed_next_action", "continue_research")
    state["recommended_next_action"] = enforce_action_consistency(
        _proposed, pe_level, dr_level, state["missing_evidence"])
    state["rationale"] = res.get("rationale") or ""
    state["decision_gate"] = res.get("decision_gate") or dict(_STUB_GATE)
    _rj = res.get("reproducible_judgment") or ""
    if state["recommended_next_action"] != _proposed:
        _rj = (_rj + f"（註:LLM 原建議 {_proposed},經訊號否決改為 "
                     f"{state['recommended_next_action']}。）")
    state["reproducible_judgment"] = _rj
    state["verdict_standalone"] = res.get("verdict_standalone", "要補證據")
    state["light"] = res.get("light", "yellow")
    state["readiness_score_delta"] = int(res.get("readiness_score_delta", 0))
