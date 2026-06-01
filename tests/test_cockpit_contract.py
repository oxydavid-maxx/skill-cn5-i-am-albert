# tests/test_cockpit_contract.py
from albert.cockpit_contract import to_audit_result
from albert.state import DECISIONS, AUDIT_VERDICTS, RISK_LEVELS, CHALLENGE_STATUSES

def _golden():
    return {"verdict": "exhausted",
        "albert_challenges": [{"challenge": "why win?", "why_albert_would_ask": "parity",
            "current_answer": "", "status": "needs_bu_judgment", "confidence": "low",
            "missing_info": "ROI", "blocking_owner": "PM", "next_action": "get ROI",
            "meeting_ready_response": "..."}],
        "weak_points": ["no ROI"], "missing_business_context": ["TAM"],
        "missing_evidence": [{"item": "roadmap", "who_can_answer": "public"}],
        "questions_albert_would_ask": ["why win?"],
        "premature_end_risk": {"level": "high"}, "research_drift_risk": {"level": "low"},
        "recommended_next_probe": [{"probe": "p", "why": "w", "priority": 1}],
        "recommended_next_action": "continue_research", "rationale": "still open",
        "readiness_score_delta": -1, "degraded": False}

def test_auditresult_fields_complete():
    ar = to_audit_result(_golden())["audit_result"]
    for k in ("verdict", "challenges", "weak_points", "premature_end_risk",
              "research_drift_risk", "recommended_next_action", "rationale", "degraded"):
        assert k in ar

def test_enums_valid():
    ar = to_audit_result(_golden())["audit_result"]
    assert ar["verdict"] in AUDIT_VERDICTS
    assert ar["recommended_next_action"] in DECISIONS
    assert ar["premature_end_risk"] in RISK_LEVELS
    assert isinstance(ar["degraded"], bool)
    for ch in ar["challenges"]:
        assert ch["status"] in CHALLENGE_STATUSES

def test_weak_points_are_strings():
    ar = to_audit_result(_golden())["audit_result"]
    assert all(isinstance(w, str) for w in ar["weak_points"])

def test_enrichment_present():
    enr = to_audit_result(_golden())["enrichment"]
    for k in ("missing_business_context", "questions_albert_would_ask",
              "recommended_next_probe", "readiness_score_delta"):
        assert k in enr
