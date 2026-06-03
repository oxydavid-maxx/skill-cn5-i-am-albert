"""Run profiles: a thin layer that flips EXISTING speed knobs as a coherent set.

'thorough' (default) = current behavior, no knobs touched.
'fast' (research-preserving) = no rework + faster/wider search; research breadth,
3-vote self-critique, and Opus strong roles are all unchanged.

A profile only setdefaults env knobs — an explicitly pre-set env value always wins.
"""
from __future__ import annotations

FAST_DEFAULTS = {
    "ALBERT_MAX_REWORK": "0",
    "ALBERT_WEBSEARCH_MAX_TURNS": "3",
    "ALBERT_RESEARCH_WIDTH": "5",
}


def resolve_profile(args_fast: bool, env) -> str:
    if args_fast:
        return "fast"
    return (env.get("ALBERT_PROFILE") or "thorough").strip().lower() or "thorough"


def apply_profile(profile: str, env) -> dict:
    """Set fast-mode knob DEFAULTS into env (setdefault semantics). Returns the
    dict of values actually applied (for logging). Unknown/thorough = no-op."""
    applied: dict = {}
    if profile == "fast":
        for k, v in FAST_DEFAULTS.items():
            if k not in env:
                env[k] = v
                applied[k] = v
    return applied
