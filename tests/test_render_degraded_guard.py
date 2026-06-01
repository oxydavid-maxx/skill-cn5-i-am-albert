# tests/test_render_degraded_guard.py
import pytest
from albert.render import enforce_degraded_guard, build_challenge
from albert.errors import DegradedEmissionError

def test_failed_green_raises():
    with pytest.raises(DegradedEmissionError):
        enforce_degraded_guard(True, "green")

def test_allowed():
    enforce_degraded_guard(True, "red"); enforce_degraded_guard(False, "green")

def test_build_has_auditresult_fields():
    c = build_challenge({"verdict": "exhausted", "albert_challenges": [], "weak_points": [],
        "premature_end_risk": {"level": "low", "grounded_in": "inferred"},
        "research_drift_risk": {"level": "low", "grounded_in": "inferred"},
        "recommended_next_action": "synthesize", "rationale": "r", "degraded": False, "run_status": "passed"})
    for k in ("verdict", "albert_challenges", "premature_end_risk", "recommended_next_action", "rationale", "degraded"):
        assert k in c
