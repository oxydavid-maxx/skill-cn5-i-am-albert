"""Regression: the quick route only works if AlbertState DECLARES `profile`.
LangGraph filters state to declared keys, so an undeclared `profile` is dropped and
_route_after_intake silently falls back to the thorough path (the 2026-06-03 bug:
`--quick` ran the full thorough pipeline)."""
from albert.state import AlbertState
from albert.graph import _route_after_intake


def test_profile_declared_in_state_schema():
    assert "profile" in AlbertState.__annotations__


def test_routing_survives_state_key_filter():
    # Simulate LangGraph keeping only schema-declared keys.
    initial = {"profile": "quick", "mode": "standalone", "_undeclared": 1}
    kept = {k: v for k, v in initial.items() if k in AlbertState.__annotations__}
    assert kept.get("profile") == "quick"
    assert _route_after_intake(kept) == "phase_quick_combined"


def test_routing_thorough_after_filter():
    initial = {"profile": "thorough", "mode": "standalone"}
    kept = {k: v for k, v in initial.items() if k in AlbertState.__annotations__}
    assert _route_after_intake(kept) == "phase_2_challenge_generation"
