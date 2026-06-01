# tests/test_action_consistency.py
from albert.signals import enforce_action_consistency

def test_high_premature_blocks_synthesize():
    a = enforce_action_consistency("synthesize", premature="high", drift="low", evidence=[])
    assert a not in ("synthesize", "terminal_stop")
    assert a == "continue_research"

def test_high_premature_blocks_terminal():
    assert enforce_action_consistency("terminal_stop", premature="high", drift="low", evidence=[]) == "continue_research"

def test_high_drift_forces_rerank_or_pull():
    assert enforce_action_consistency("continue_research", premature="low", drift="high", evidence=[]) in ("rerank", "pull_human")

def test_customer_residual_forces_push_or_pull():
    ev = [{"item": "x", "who_can_answer": "customer"}, {"item": "y", "who_can_answer": "customer"}]
    assert enforce_action_consistency("synthesize", premature="low", drift="low", evidence=ev) in ("push_human", "pull_human")

def test_consistent_action_passes_through():
    assert enforce_action_consistency("branch", premature="low", drift="low", evidence=[]) == "branch"
