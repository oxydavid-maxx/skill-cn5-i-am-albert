"""Reference mapping: albert_challenge.json -> cockpit AuditResult (+ enrichment for the
gap-audit A2 fields the cockpit's AuditResult does not yet carry). Proves the R17 seam.
The cockpit owns the production adapter; this is the producer-side proof."""
from __future__ import annotations

_CHALLENGE_FIELDS = ["challenge", "why_albert_would_ask", "current_answer", "status",
                     "confidence", "evidence_refs", "missing_info", "blocking_owner",
                     "next_action", "meeting_ready_response"]


def _entry(ch: dict) -> dict:
    e = {k: ch.get(k, "") for k in _CHALLENGE_FIELDS}
    e["evidence_refs"] = ch.get("evidence_refs", [])
    return e


def to_audit_result(challenge: dict) -> dict:
    return {
        "audit_result": {                                   # the cockpit's AuditResult (load-bearing)
            "verdict": challenge.get("verdict", "rework"),
            "challenges": [_entry(c) for c in challenge.get("albert_challenges", [])],
            "weak_points": [w if isinstance(w, str) else str(w) for w in challenge.get("weak_points", [])],
            "premature_end_risk": (challenge.get("premature_end_risk") or {}).get("level", "low"),
            "research_drift_risk": (challenge.get("research_drift_risk") or {}).get("level", "low"),
            "recommended_next_action": challenge.get("recommended_next_action"),
            "rationale": challenge.get("rationale", ""),
            "degraded": bool(challenge.get("degraded", False)),
        },
        "enrichment": {                                     # gap-audit A2 (cockpit will add these fields)
            "missing_business_context": challenge.get("missing_business_context", []),
            "questions_albert_would_ask": challenge.get("questions_albert_would_ask", []),
            "recommended_next_probe": challenge.get("recommended_next_probe", []),
            "readiness_score_delta": challenge.get("readiness_score_delta", 0),
            "premature_end_atoms": (challenge.get("premature_end_risk") or {}).get("atoms", {}),
            "grounded_in": (challenge.get("premature_end_risk") or {}).get("grounded_in", "inferred"),
        },
    }
