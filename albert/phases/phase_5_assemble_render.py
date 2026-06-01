"""Phase 5: compute AuditVerdict + degraded, standalone verdict+light (degraded guard),
assemble the AuditResult-aligned contract, render + email."""
import sys
from pathlib import Path
from albert.errors import VisibilityContractError, DegradedEmissionError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
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

    ctx = (f"Ambiguities: {state.get('top_ambiguities')}\nChallenges: {len(state.get('albert_challenges', []))}\n"
           f"premature_end: {state.get('premature_end_risk', {}).get('level')}\n"
           f"missing_evidence: {state.get('missing_evidence')}\n")
    try:
        v = call_claude(model=model_for_role("verdict_render"), system=load_prompt("verdict_render"),
                        user=ctx, json_schema=schemas.VERDICT, purpose="verdict_render")
        vs, light, delta = v.get("verdict_standalone", "要補證據"), v.get("light", "yellow"), int(v.get("readiness_score_delta", 0))
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_5 verdict failed: {type(e).__name__}: {str(e)[:200]}; refuse\n")
        vs, light, delta, degraded = "產品定義不完整", "red", -2, True
        state["degraded"], state["run_status"] = True, "failed"

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
