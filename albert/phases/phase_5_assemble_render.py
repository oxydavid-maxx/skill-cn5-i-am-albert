"""Phase 5: compute AuditVerdict + degraded, apply the degraded guard to the
verdict+light produced by phase 4, assemble the AuditResult-aligned contract,
render + email. NO LLM call here — the verdict fields are produced by phase 4's
merged signals+verdict call and read from state."""
from pathlib import Path
from albert.errors import DegradedEmissionError
from albert.render import enforce_degraded_guard, write_challenge_json, write_report
from albert.email_delivery import send_email

_STATUS_KEYS = [f"phase_{i}_status" for i in range(5)]


def _audit_verdict(state: dict, degraded: bool) -> str:
    """Map the run to the cockpit AuditVerdict {continue, exhausted, rework}.
    rework if the self-critique still wanted rework or any dangerous ambiguity is unresolved-ish;
    exhausted if the loop exhausted cleanly; continue if premature_end is high (more research warranted)."""
    if state.get("phase_3_verdict") == "REWORK":
        return "rework"
    if (state.get("premature_end_risk", {}) or {}).get("level") == "high":
        return "continue"
    return "exhausted"


def phase_5_assemble_render(state: dict) -> dict:
    degraded = any(state.get(k) == "failed" for k in _STATUS_KEYS)
    state["degraded"] = degraded
    state["run_status"] = "failed" if degraded else "passed"
    state["verdict"] = _audit_verdict(state, degraded)

    # Verdict fields are produced by phase 4's merged signals+verdict call; read
    # from state (no LLM call here). Fall back to a refuse-grade verdict only if
    # phase 4 somehow left them unset.
    vs = state.get("verdict_standalone", "要補證據")
    light = state.get("light", "yellow")
    delta = int(state.get("readiness_score_delta", 0))

    try:
        enforce_degraded_guard(degraded, light)
    except DegradedEmissionError:
        light = "red"
        if vs == "可推進":
            vs = "要補證據"

    state["verdict_standalone"], state["light"], state["readiness_score_delta"] = vs, light, delta
    run_dir = Path(state["run_dir"])
    state["challenge_json_path"] = write_challenge_json(state, run_dir)
    state["report_path"] = write_report(state, run_dir)

    if state.get("mode") == "standalone" and state.get("user_email"):
        try:
            state["email_delivery_result"] = send_email(to=state["user_email"],
                subject=f"[Albert] {vs} — {state['proposal'].get('title','review')}", body_path=state["report_path"])
        except Exception as e:
            state["email_delivery_result"] = "failed"
            state["email_delivery_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    state["phase_5_complete"] = True
    return state
