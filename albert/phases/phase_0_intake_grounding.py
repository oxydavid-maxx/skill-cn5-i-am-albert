"""Phase 0: parse §20 input + META-research grounding (wave-1 -> reflect -> wave-2).
Meta-research only; object-research is the cockpit's job. websearch() never raises."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude, websearch
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas

_QUERIES_SCHEMA = {"type": "object", "properties": {
    "queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5}},
    "required": ["queries"]}

_CARRY = ["current_answer", "original_objective", "meeting_context", "output_purpose",
          "issue_map", "challenge_map", "evidence", "skeptic_output", "source_critic_output",
          "readiness_scores", "recent_research_actions", "research_state", "proposal"]


def phase_0_intake_grounding(state: dict) -> dict:
    inp = state["albert_input"]
    state["mode"] = inp.get("mode", "standalone")
    for k in _CARRY:
        state[k] = inp.get(k, "" if k in ("current_answer", "original_objective", "meeting_context", "output_purpose") else ({} if k in ("research_state", "readiness_scores", "proposal") else []))

    ctx = (f"Current answer:\n{state['current_answer'][:6000]}\n\n"
           f"Domain: {state['proposal'].get('domain','')}\nMeeting: {state.get('meeting_context','')}\n"
           f"Output purpose: {state.get('output_purpose','')}\n")
    status, research, meta = "passed", [], {}
    try:
        plan = call_claude(model=model_for_role("intake_grounding"),
                           system=load_prompt("intake_grounding"), user=ctx,
                           json_schema=_QUERIES_SCHEMA, purpose="intake_grounding")
        wave1 = [websearch(q) for q in (plan.get("queries") or [])[:5]]
        research.extend(wave1)
        refl_ctx = ctx + "\nWave-1 results:\n" + "\n".join(
            f"- {r['query']}: {str(r.get('results',''))[:300]}" for r in wave1)
        meta = call_claude(model=model_for_role("intake_grounding"),
                           system=load_prompt("search_reflection"), user=refl_ctx,
                           json_schema=schemas.SEARCH_REFLECTION, purpose="search_reflection")
        research.extend(websearch(q) for q in (meta.get("wave2_queries") or [])[:4])
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_0 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        status = "failed"
    state["research"], state["meta_question"] = research, meta or {}
    state["phase_0_status"], state["phase_0_complete"] = status, True
    return state
