"""Quick mode: ONE Opus call doing challenges + inline self-critique + signals + verdict,
then deterministic signals.py application. No separate debate/rework round (the ~80% cut)."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt, research_refs
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


def phase_quick_combined(state: dict) -> dict:
    ctx = (f"Output purpose: {state.get('output_purpose','')}\n\n"
           f"Current answer:\n{state.get('current_answer','')[:6000]}\n\n"
           f"Research (cite [Rk] in evidence_refs):\n{research_refs(state.get('research', []))}\n")
    status = "passed"
    try:
        res = call_claude(model=model_for_role("challenge_generation"),
                          system=load_prompt("albert_persona") + "\n\n" + load_prompt("quick_combined"),
                          user=ctx, json_schema=schemas.QUICK_COMBINED, purpose="quick_combined")
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_quick failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = dict(_STUB), "failed"
    challenges = res.get("albert_challenges") or _STUB["albert_challenges"]
    state["albert_challenges"] = challenges
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
    body = (L.header("PHASE Q ─ 快速審查(quick)")
            + "\n" + deliberation.render_challenges(state, header=False)
            + "\n\n(quick 模式:單次審查 + inline 自我檢查,無多票辯論)\n\n"
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
    deliberation.block("phase_quick_combined", "PHASE Q ─ 快速審查(quick)", body)
    return state
