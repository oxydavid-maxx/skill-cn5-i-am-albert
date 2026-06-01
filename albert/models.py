"""Model routing. Reasoning-heavy roles stay on the strong session default."""
from __future__ import annotations
import os

ENVIRONMENT_DEFAULT_MODEL_LABEL = "environment-default"
# SOUL roles: reasoning-heavy, stay on the strong session default (Opus). None -> CLI default.
_SOUL_ROLES = frozenset({"challenge_generation", "self_critique_audit"})
# STRUCTURAL roles: routed to the latest Sonnet for speed unless overridden.
_STRUCTURAL_ROLES = frozenset({"intake_grounding", "ambiguity_hunt",
                               "signals_action_gate", "verdict_render"})
_SONNET_ALIAS = "sonnet"  # CLI --model alias resolves to the latest Sonnet
_FAST_MODEL_ENV = "ALBERT_FAST_MODEL"


def model_for_role(role: str) -> str | None:
    # SOUL roles always ride the session default (Opus); ignore any fast override.
    if role in _SOUL_ROLES:
        return None
    override = (os.environ.get(_FAST_MODEL_ENV) or "").strip()
    if override:
        return override
    if role in _STRUCTURAL_ROLES:
        return _SONNET_ALIAS
    # Unknown roles fall through to env (already empty here) -> session default.
    return None


def model_label(model: str | None) -> str:
    return model or ENVIRONMENT_DEFAULT_MODEL_LABEL
