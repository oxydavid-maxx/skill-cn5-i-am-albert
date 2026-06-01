"""Model routing. Reasoning-heavy roles stay on the strong session default."""
from __future__ import annotations
import os

ENVIRONMENT_DEFAULT_MODEL_LABEL = "environment-default"
_STRONG_ROLES = frozenset({"challenge_generation", "self_critique_audit",
                           "signals_action_gate", "verdict_render"})
_FAST_MODEL_ENV = "ALBERT_FAST_MODEL"


def model_for_role(role: str) -> str | None:
    if role in _STRONG_ROLES:
        return None
    return (os.environ.get(_FAST_MODEL_ENV) or "").strip() or None


def model_label(model: str | None) -> str:
    return model or ENVIRONMENT_DEFAULT_MODEL_LABEL
