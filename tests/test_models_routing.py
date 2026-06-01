# tests/test_models_routing.py
from albert.models import model_for_role, model_label

def test_soul_roles_default_to_opus():
    # SOUL roles return None -> session-default (Opus)
    for r in ("challenge_generation", "self_critique_audit"):
        assert model_for_role(r) is None

def test_structural_roles_default_to_sonnet():
    for r in ("intake_grounding", "ambiguity_hunt", "signals_action_gate", "verdict_render"):
        assert model_for_role(r) == "sonnet"

def test_fast_env_overrides_structural(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODEL", "claude-sonnet-4-6")
    assert model_for_role("ambiguity_hunt") == "claude-sonnet-4-6"
    assert model_for_role("intake_grounding") == "claude-sonnet-4-6"
    # SOUL roles ignore the override and stay on session default
    assert model_for_role("self_critique_audit") is None
    assert model_for_role("challenge_generation") is None

def test_unknown_role_falls_through_to_env(monkeypatch):
    assert model_for_role("some_other_role") is None
    monkeypatch.setenv("ALBERT_FAST_MODEL", "claude-sonnet-4-6")
    assert model_for_role("some_other_role") == "claude-sonnet-4-6"

def test_label():
    assert model_label(None) == "environment-default"
