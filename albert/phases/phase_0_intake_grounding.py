"""Phase 0: parse §20 input + META-research grounding.

Default: ONE intake-planning call proposes ALL queries (object- AND meta-level) upfront,
then a SINGLE parallel wave runs them concurrently — no reflection round-trip, no second
sequential wave. Set ALBERT_RESEARCH_REFLECT=1 to retain the deeper two-wave + reflection
path. Meta-research only; object-research is the cockpit's job. websearch() never raises."""
import os
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude, websearch
from albert.parallel import parallel_map
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert import deliberation

# Single-call schema: queries (object- + meta-level) PLUS a short meta_question framing
# string so Phase 2 has a higher-level question without a separate reflection call.
_QUERIES_SCHEMA = {"type": "object", "properties": {
    "queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
    "meta_question": {"type": "string"}},
    "required": ["queries"]}

def _research_width() -> int:
    try:
        return max(1, int(os.environ.get("ALBERT_RESEARCH_WIDTH", "3")))
    except (TypeError, ValueError):
        return 3


def _research_max_queries() -> int:
    try:
        return max(1, int(os.environ.get("ALBERT_RESEARCH_MAX_QUERIES", "8")))
    except (TypeError, ValueError):
        return 8


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
    reflect = os.environ.get("ALBERT_RESEARCH_REFLECT") == "1"
    try:
        plan = call_claude(model=model_for_role("intake_grounding"),
                           system=load_prompt("intake_grounding"), user=ctx,
                           json_schema=_QUERIES_SCHEMA, purpose="intake_grounding")
        if reflect:
            # Deeper path: two sequential waves with a reflection round-trip between them.
            wave1 = parallel_map(websearch, (plan.get("queries") or [])[:5])
            research.extend(wave1)
            refl_ctx = ctx + "\nWave-1 results:\n" + "\n".join(
                f"- {r['query']}: {str(r.get('results',''))[:300]}" for r in wave1)
            meta = call_claude(model=model_for_role("intake_grounding"),
                               system=load_prompt("search_reflection"), user=refl_ctx,
                               json_schema=schemas.SEARCH_REFLECTION, purpose="search_reflection")
            research.extend(parallel_map(websearch, (meta.get("wave2_queries") or [])[:4]))
        else:
            # Default path: ALL queries (object- + meta-level) run concurrently,
            # but bounded to 3 at a time. Each websearch spawns its own `claude`
            # subprocess; >3 simultaneous inits triggers "Control request timeout:
            # initialize" under load, which fails the whole wave and leaves the
            # review UNGROUNDED. 3-at-a-time keeps searches concurrent without the
            # init-timeout.
            queries = (plan.get("queries") or [])[:_research_max_queries()]
            research.extend(parallel_map(websearch, queries, max_workers=_research_width()))
            # Meta framing comes from the intake plan, not a separate reflection call.
            mq = plan.get("meta_question")
            meta = {"higher_level_question": mq} if mq else {}
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_0 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        status = "failed"
    state["research"], state["meta_question"] = research, meta or {}
    state["phase_0_status"], state["phase_0_complete"] = status, True
    deliberation.block("phase_0_intake_grounding", "Phase 0 — Research grounding",
                       deliberation.render_research(state))
    return state
