"""StructuredOutput JSON schemas, aligned to the cockpit's AuditResult. Top-level type 'object'."""

GENERATOR_ENUM = ["winning", "first_principle", "timing",
                  "competitor", "owner_business", "convergence_redteam"]
STATUS_ENUM = ["answered", "partially_answered", "needs_external_research", "needs_internal_data",
               "needs_bu_judgment", "needs_albert_decision", "needs_source_validation", "blocked"]
DECISION_ENUM = ["continue_research", "branch", "rerank", "pull_human",
                 "push_human", "synthesize", "pause", "terminal_stop"]
VERDICT_ENUM = ["continue", "exhausted", "rework"]
LEVEL_ENUM = ["low", "medium", "high"]
STRENGTH_ENUM = ["weak", "medium", "strong"]

SEARCH_REFLECTION = {
    "type": "object",
    "properties": {
        "reframing": {"type": "string"},
        "higher_level_question": {"type": "string"},
        "wave2_queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
    },
    "required": ["higher_level_question", "wave2_queries"],
}

AMBIGUITY_HUNT = {
    "type": "object",
    "properties": {"top_ambiguities": {"type": "array", "items": {"type": "object", "properties": {
        "term": {"type": "string"}, "why_dangerous": {"type": "string"},
        "precise_question": {"type": "string"}},
        "required": ["term", "why_dangerous", "precise_question"]}, "minItems": 3, "maxItems": 3}},
    "required": ["top_ambiguities"],
}

_CHALLENGE_ITEM = {
    "type": "object",
    "properties": {
        "challenge": {"type": "string"},
        "why_albert_would_ask": {"type": "string"},
        "current_answer": {"type": "string"},
        "status": {"type": "string", "enum": STATUS_ENUM},
        "confidence": {"type": "string", "enum": LEVEL_ENUM},
        "severity": {"type": "string", "enum": LEVEL_ENUM},
        "current_answer_strength": {"type": "string", "enum": STRENGTH_ENUM},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "missing_info": {"type": "string"},
        "blocking_owner": {"type": "string"},
        "next_action": {"type": "string"},
        "meeting_ready_response": {"type": "string"},
        "recommended_probe": {"type": "string"},
        "generator": {"type": "string", "enum": GENERATOR_ENUM},
        "bone": {"type": "integer", "minimum": 1, "maximum": 12},
        "high_impact": {"type": "boolean"},
    },
    "required": ["challenge", "why_albert_would_ask", "status", "severity",
                 "current_answer_strength", "generator", "bone"],
}

CHALLENGE_GENERATION = {
    "type": "object",
    "properties": {
        "albert_challenges": {"type": "array", "items": _CHALLENGE_ITEM, "minItems": 1},
        "weak_points": {"type": "array", "items": {"type": "string"}},
        "missing_business_context": {"type": "array", "items": {"type": "string"}},
        "would_survive_leadership": {"type": "boolean"},
    },
    "required": ["albert_challenges", "weak_points", "would_survive_leadership"],
}

SELF_CRITIQUE_AUDIT = {
    "type": "object",
    "properties": {
        "round": {"type": "integer"},
        "weaknesses": {"type": "array", "items": {"type": "object", "properties": {
            "challenge_index": {"type": ["integer", "null"]},
            "classification": {"type": "string", "enum": ["addressable", "residual"]},
            "issue": {"type": "string"}, "suggested_sharpening": {"type": "string"}},
            "required": ["classification", "issue"]}},
        "verdict": {"type": "string", "enum": ["continue", "exhausted", "rework"]},
    },
    "required": ["round", "weaknesses", "verdict"],
}

# Phase 4 LLM produces atoms + a PROPOSED action + rationale; signals.py computes
# the risk levels and vetoes an action inconsistent with the signals.
SIGNALS_ACTION_GATE = {
    "type": "object",
    "properties": {
        "missing_evidence": {"type": "array", "items": {"type": "object", "properties": {
            "item": {"type": "string"},
            "who_can_answer": {"type": "string", "enum": ["AI", "public", "internal", "customer"]}},
            "required": ["item", "who_can_answer"]}},
        "questions_albert_would_ask": {"type": "array", "items": {"type": "string"}},
        "premature_end_atoms": {"type": "object", "properties": {
            "open_high_impact_challenges": {"type": "integer", "minimum": 0},
            "new_info_rate": {"type": "string", "enum": ["high", "medium", "low", "none", "unknown"]},
            "challenge_map_mostly_classified": {"type": "boolean"},
            "unresolved_are_human_data_decision_only": {"type": "boolean"},
            "meta_question_search_found_new_high_impact_angle": {"type": "boolean"}},
            "required": ["open_high_impact_challenges", "new_info_rate"]},
        "drift_atoms": {"type": "object", "properties": {
            "current_focus_in_original_high_value_set": {"type": "boolean"},
            "high_value_branch_ignored": {"type": "boolean"}}},
        "recommended_next_probe": {"type": "array", "items": {"type": "object", "properties": {
            "probe": {"type": "string"}, "why": {"type": "string"},
            "kind": {"type": "string", "enum": ["meta", "object"]},
            "impact": {"type": "string", "enum": LEVEL_ENUM},
            "answerability": {"type": "string", "enum": LEVEL_ENUM}},
            "required": ["probe", "why"]}},
        "proposed_next_action": {"type": "string", "enum": DECISION_ENUM},
        "rationale": {"type": "string"},
        "decision_gate": {"type": "object", "properties": {
            "can_decide_now": {"type": "array", "items": {"type": "string"}},
            "cannot_decide": {"type": "array", "items": {"type": "string"}},
            "owners": {"type": "array", "items": {"type": "object", "properties": {
                "area": {"type": "string"}, "owner": {"type": "string"}},
                "required": ["area", "owner"]}}},
            "required": ["can_decide_now", "cannot_decide", "owners"]},
        "reproducible_judgment": {"type": "string"},
    },
    "required": ["premature_end_atoms", "proposed_next_action", "decision_gate"],
}

VERDICT = {
    "type": "object",
    "properties": {
        "verdict_standalone": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
        "readiness_score_delta": {"type": "integer", "minimum": -2, "maximum": 2},
    },
    "required": ["verdict_standalone", "light", "readiness_score_delta"],
}

# Phase 4 + Phase 5 merged: the signals/action-gate atoms PLUS the standalone
# verdict-presentation fields, produced in ONE structured-output call. The
# system still computes risk LEVELS and vetoes the action from signals.py; only
# the verdict-presentation fields below come straight from the LLM.
SIGNALS_VERDICT_MERGED = {
    "type": "object",
    "properties": {
        **SIGNALS_ACTION_GATE["properties"],
        "verdict_standalone": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
        "readiness_score_delta": {"type": "integer", "minimum": -2, "maximum": 2},
    },
    "required": SIGNALS_ACTION_GATE["required"] + ["verdict_standalone", "light", "readiness_score_delta"],
}

_RISK = {"type": "object", "properties": {
    "level": {"type": "string", "enum": LEVEL_ENUM}, "atoms": {"type": "object"},
    "grounded_in": {"type": "string", "enum": ["research_state", "inferred"]},
    "why": {"type": "string"}, "low_confidence": {"type": "boolean"}}, "required": ["level", "grounded_in"]}

ALBERT_CHALLENGE = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": VERDICT_ENUM},
        "audited_answer": {"type": "string"},
        "would_survive_leadership": {"type": "boolean"},
        "top_ambiguities": AMBIGUITY_HUNT["properties"]["top_ambiguities"],
        "albert_challenges": {"type": "array", "items": _CHALLENGE_ITEM},
        "weak_points": {"type": "array", "items": {"type": "string"}},
        "missing_business_context": {"type": "array", "items": {"type": "string"}},
        "missing_evidence": SIGNALS_ACTION_GATE["properties"]["missing_evidence"],
        "questions_albert_would_ask": {"type": "array", "items": {"type": "string"}},
        "premature_end_risk": _RISK,
        "research_drift_risk": _RISK,
        "recommended_next_probe": SIGNALS_ACTION_GATE["properties"]["recommended_next_probe"],
        "recommended_next_action": {"type": "string", "enum": DECISION_ENUM},
        "rationale": {"type": "string"},
        "decision_gate": SIGNALS_ACTION_GATE["properties"]["decision_gate"],
        "readiness_score_delta": {"type": "integer", "minimum": -2, "maximum": 2},
        "reproducible_judgment": {"type": "string"},
        "degraded": {"type": "boolean"},
        "run_status": {"type": "string", "enum": ["passed", "failed"]},
        "verdict_standalone": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
    },
    "required": ["verdict", "albert_challenges", "weak_points", "premature_end_risk",
                 "research_drift_risk", "recommended_next_action", "rationale", "degraded"],
}

ALBERT_INPUT = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["cockpit", "standalone"]},
        "current_answer": {"type": "string"},
        "original_objective": {"type": "string"},
        "meeting_context": {"type": "string"},
        "output_purpose": {"type": "string",
            "enum": ["meeting_defense", "decision_readiness", "find_blockers", "exec_memo"]},
        "issue_map": {"type": "array", "items": {"type": "object"}},
        "challenge_map": {"type": "array", "items": {"type": "object"}},
        "evidence": {"type": "array", "items": {"type": "object"}},
        "skeptic_output": {"type": "array", "items": {"type": "string"}},
        "source_critic_output": {"type": "array", "items": {"type": "string"}},
        "readiness_scores": {"type": "object"},
        "recent_research_actions": {"type": "array", "items": {"type": "string"}},
        "research_state": {"type": "object"},
        "proposal": {"type": "object", "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, "domain": {"type": "string"}}},
    },
    "required": ["current_answer", "mode"],
}
