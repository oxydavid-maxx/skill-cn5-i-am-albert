"""Flash mode: ONE Opus call, NO research, bypasses phase_0/2/3/4. Albert's one-shot judgment."""
from albert.sdk_client import call_claude  # re-exported so tests/_resolve_call_claude can monkeypatch this module
from albert.phases._combined import combined_audit


def phase_flash(state: dict) -> dict:
    inp = state.get("albert_input") or {}
    state.setdefault("current_answer", inp.get("current_answer", ""))
    state["output_purpose"] = state.get("output_purpose") or inp.get("output_purpose", "")
    state["original_objective"] = state.get("original_objective") or inp.get("original_objective", "")
    state["meeting_context"] = state.get("meeting_context") or inp.get("meeting_context", "")
    state["proposal"] = state.get("proposal") or inp.get("proposal", {}) or {}
    state["research"] = []
    return combined_audit(
        state, prompt="flash_combined", node="phase_flash",
        banner="PHASE F ─ 閃電審查(flash)", research_text="",
        note="(flash 模式:單次 Opus 判斷,無研究、無辯論)")
