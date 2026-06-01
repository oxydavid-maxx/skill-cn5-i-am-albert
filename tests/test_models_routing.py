# tests/test_models_routing.py
from albert.models import model_for_role, model_label

def test_strong_roles_default():
    for r in ("challenge_generation", "self_critique_audit", "signals_action_gate", "verdict_render"):
        assert model_for_role(r) is None

def test_fast_env_routes_non_strong(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODEL", "claude-sonnet-4-6")
    assert model_for_role("ambiguity_hunt") == "claude-sonnet-4-6"
    assert model_for_role("self_critique_audit") is None

def test_label():
    assert model_label(None) == "environment-default"
