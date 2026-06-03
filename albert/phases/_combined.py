"""Shared one-call audit core for quick + flash profiles.

ONE call_claude(QUICK_COMBINED) + apply_signals + contract fields + deliberation block.
quick passes research_text (from research_refs); flash passes "" (no research)."""
import sys
import importlib
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas, deliberation
from albert import delib_layout as L
from albert.signals_apply import apply_signals

_STUB = {"albert_challenges": [{"challenge": "(LLM unavailable — re-run Albert)",
         "why_albert_would_ask": "n/a", "status": "blocked", "severity": "high",
         "current_answer_strength": "weak", "generator": "winning", "bone": 2}],
         "weak_points": [], "missing_business_context": [], "would_survive_leadership": False,
         "top_ambiguities": [{"term": "(LLM unavailable)", "why_dangerous": "n/a",
                              "precise_question": "re-run"} for _ in range(3)],
         "premature_end_atoms": {}, "drift_atoms": {}, "proposed_next_action": "continue_research",
         "decision_gate": {"can_decide_now": [], "cannot_decide": ["(LLM unavailable)"], "owners": []},
         "reproducible_judgment": "", "verdict_standalone": "產品定義不完整", "light": "red",
         "readiness_score_delta": -2}


def _resolve_call_claude(node: str):
    """Resolve call_claude from the calling phase module so tests that
    monkeypatch <phase_module>.call_claude keep working; fall back to ours."""
    try:
        mod = importlib.import_module(f"albert.phases.{node}")
        return getattr(mod, "call_claude")
    except Exception:
        return call_claude


def combined_audit(state: dict, *, prompt: str, node: str, banner: str,
                   research_text: str, note: str) -> dict:
    ctx = (f"Output purpose: {state.get('output_purpose','')}\n\n"
           f"Current answer:\n{state.get('current_answer','')[:6000]}\n")
    if research_text:
        ctx += f"\nResearch (cite [Rk] in evidence_refs):\n{research_text}\n"
    status = "passed"
    _call = _resolve_call_claude(node)
    try:
        res = _call(model=model_for_role("challenge_generation"),
                    system=load_prompt("albert_persona") + "\n\n" + load_prompt(prompt),
                    user=ctx, json_schema=schemas.QUICK_COMBINED, purpose=prompt)
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] {node} failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = dict(_STUB), "failed"
    state["albert_challenges"] = res.get("albert_challenges") or _STUB["albert_challenges"]
    state["weak_points"] = res.get("weak_points") or []
    state["missing_business_context"] = res.get("missing_business_context") or []
    state["would_survive_leadership"] = bool(res.get("would_survive_leadership", False))
    amb = res.get("top_ambiguities") or []
    if not isinstance(amb, list) or len(amb) < 3:
        amb = (amb if isinstance(amb, list) else []) + _STUB["top_ambiguities"]
    state["top_ambiguities"] = amb[:3]
    apply_signals(state, res)
    state["verdict"] = "exhausted"
    state["phase_2_status"] = status
    state["phase_4_status"], state["phase_4_complete"] = status, True
    body = (L.header(banner)
            + "\n" + deliberation.render_challenges(state, header=False)
            + f"\n\n{note}\n\n"
            + deliberation.render_signals({
                "premature_end_risk": state["premature_end_risk"],
                "research_drift_risk": state["research_drift_risk"],
                "proposed_next_action": res.get("proposed_next_action", "?"),
                "recommended_next_action": state["recommended_next_action"]}, header=False)
            + "\n\n" + deliberation.render_verdict({
                "verdict_standalone": state["verdict_standalone"], "light": state["light"],
                "readiness_score_delta": state["readiness_score_delta"],
                "recommended_next_action": state["recommended_next_action"],
                "reproducible_judgment": state["reproducible_judgment"]}, header=False))
    deliberation.block(node, banner, body)
    return state
