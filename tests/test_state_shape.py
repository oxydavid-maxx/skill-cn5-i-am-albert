# tests/test_state_shape.py
from albert.state import (AlbertState, GENERATORS, CHALLENGE_STATUSES,
                          DECISIONS, AUDIT_VERDICTS, RISK_LEVELS)

def test_generators_six():
    assert len(GENERATORS) == 6 and "convergence_redteam" in GENERATORS

def test_statuses_eight():
    assert len(CHALLENGE_STATUSES) == 8 and "needs_albert_decision" in CHALLENGE_STATUSES

def test_decisions_eight():
    assert DECISIONS == ["continue_research", "branch", "rerank", "pull_human",
                         "push_human", "synthesize", "pause", "terminal_stop"]

def test_audit_verdicts():
    assert AUDIT_VERDICTS == ["continue", "exhausted", "rework"]

def test_risk_levels():
    assert RISK_LEVELS == ["low", "medium", "high"]

def test_total_false():
    s: AlbertState = {}
    s["current_answer"] = "x"
    assert s["current_answer"] == "x"
