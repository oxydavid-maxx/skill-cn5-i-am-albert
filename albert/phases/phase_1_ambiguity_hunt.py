"""Phase 1 (bone 1): top-3 dangerous ambiguities in the current answer."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas


def _stub():
    return [{"term": "(LLM unavailable)", "why_dangerous": "review could not run",
             "precise_question": "re-run Albert when transport is available"} for _ in range(3)]


def phase_1_ambiguity_hunt(state: dict) -> dict:
    digest = "\n".join(f"- {r.get('query','')}: {str(r.get('results',''))[:300]}"
                       for r in (state.get("research") or [])[:3])
    ctx = f"Current answer:\n{state.get('current_answer','')[:6000]}\n\nResearch:\n{digest}\n"
    status = "passed"
    try:
        res = call_claude(model=model_for_role("ambiguity_hunt"), system=load_prompt("ambiguity_hunt"),
                          user=ctx, json_schema=schemas.AMBIGUITY_HUNT, purpose="ambiguity_hunt")
        top = res.get("top_ambiguities") or []
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_1 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        top, status = _stub(), "failed"
    if not isinstance(top, list) or len(top) < 3:
        top = (top or []) + _stub()
    state["top_ambiguities"], state["phase_1_status"], state["phase_1_complete"] = top[:3], status, True
    return state
