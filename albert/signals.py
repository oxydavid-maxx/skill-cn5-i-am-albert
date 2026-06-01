"""Deterministic rule engine for the loop signals + action-consistency guard.

Risk levels are pure functions of named atoms (spec §4 / consumer §9.3) — never an
LLM gestalt. The recommended next action is LLM-proposed but vetoed here when it
contradicts the signals."""
from __future__ import annotations

_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0, "unknown": 1}


def grounding_of(research_state: dict | None) -> str:
    if research_state and any(research_state.get(k) for k in
                              ("branches_explored", "branches_open", "rounds_so_far",
                               "new_info_rate", "stage_summary")):
        return "research_state"
    return "inferred"


def premature_end_level(atoms: dict) -> str:
    """High = §9.3 'safe to stop' conditions NOT all met. 0 violations->low, 1->medium, >=2->high."""
    violations = 0
    if atoms.get("new_info_rate") not in ("low", "none"):
        violations += 1
    if atoms.get("meta_question_search_found_new_high_impact_angle"):
        violations += 1
    if int(atoms.get("open_high_impact_challenges", 0) or 0) > 0:
        violations += 1
    if not atoms.get("challenge_map_mostly_classified", False):
        violations += 1
    if not atoms.get("unresolved_are_human_data_decision_only", False):
        violations += 1
    if violations == 0:
        return "low"
    return "high" if violations >= 2 else "medium"


def drift_level(atoms: dict) -> str:
    in_set = atoms.get("current_focus_in_original_high_value_set", True)
    ignored = atoms.get("high_value_branch_ignored", False)
    if in_set and not ignored:
        return "low"
    if (not in_set) and ignored:
        return "high"
    return "medium"


def rank_next_probe(probes: list[dict]) -> list[dict]:
    def key(p):
        return (_RANK.get(p.get("impact", "medium"), 2), _RANK.get(p.get("answerability", "medium"), 2))
    ranked = sorted(list(probes or []), key=key, reverse=True)
    for i, p in enumerate(ranked, 1):
        p["priority"] = i
    return ranked


def build_risk(level: str, atoms: dict, research_state: dict | None, why: str = "") -> dict:
    grounded = grounding_of(research_state)
    return {"level": level, "atoms": atoms, "grounded_in": grounded,
            "why": why, "low_confidence": grounded == "inferred"}


def enforce_action_consistency(proposed: str, premature: str, drift: str, evidence: list[dict]) -> str:
    """Veto an LLM-proposed next action that contradicts the rule-grounded signals.
    Albert RECOMMENDS; the cockpit still decides. Order: premature > drift > evidence."""
    if premature == "high" and proposed in ("synthesize", "terminal_stop"):
        return "continue_research"           # not done — keep researching
    if drift == "high" and proposed not in ("rerank", "pull_human"):
        return "rerank"                       # off-track — re-rank toward the objective
    customer_only = [e for e in (evidence or []) if e.get("who_can_answer") == "customer"]
    if len(customer_only) >= 2 and proposed not in ("push_human", "pull_human"):
        return "push_human"                   # the blocker is the customer, not more AI research
    return proposed
