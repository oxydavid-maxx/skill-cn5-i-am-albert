"""Quick mode: ONE Opus call (challenges + inline self-critique + signals + verdict),
no separate debate/rework round. Thin wrapper over combined_audit (shared with flash)."""
from albert.sdk_client import call_claude  # re-exported so tests can monkeypatch this module
from albert.utils import research_refs
from albert.phases._combined import combined_audit


def phase_quick_combined(state: dict) -> dict:
    return combined_audit(
        state, prompt="quick_combined", node="phase_quick_combined",
        banner="PHASE Q ─ 快速審查(quick)",
        research_text=research_refs(state.get("research", [])),
        note="(quick 模式:單次審查 + inline 自我檢查,無多票辯論)")
