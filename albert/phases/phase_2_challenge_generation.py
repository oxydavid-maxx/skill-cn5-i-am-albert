"""Phase 2 (bones 2-11): generate albert_challenges against the current answer, building on
the Skeptic + Source Critic output. Rework loop feeds prior addressable sharpenings back."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert import deliberation


def _stub():
    return {"albert_challenges": [{"challenge": "(LLM unavailable — re-run Albert)",
            "why_albert_would_ask": "n/a", "status": "blocked", "severity": "high",
            "current_answer_strength": "weak", "generator": "winning", "bone": 2}],
            "weak_points": [], "missing_business_context": [], "would_survive_leadership": False}


def _amb_stub():
    return [{"term": "(LLM unavailable)", "why_dangerous": "review could not run",
             "precise_question": "re-run Albert"} for _ in range(3)]


def _prior_sharpenings(state):
    rounds = state.get("phase_3_rounds") or []
    if not rounds:
        return ""
    fixes = [w.get("suggested_sharpening", "") for w in rounds[-1].get("weaknesses", [])
             if isinstance(w, dict) and w.get("classification") == "addressable" and w.get("suggested_sharpening")]
    return ("Prior audit said these were too weak — sharpen them:\n" + "\n".join(f"- {f}" for f in fixes) + "\n\n") if fixes else ""


def _lines(items, n=4):
    return "\n".join(f"- {str(i)[:200]}" for i in (items or [])[:n])


def phase_2_challenge_generation(state: dict) -> dict:
    meta = state.get("meta_question") or {}
    ctx = (f"{_prior_sharpenings(state)}"
           f"Output purpose: {state.get('output_purpose','')}\n\n"
           f"Current answer:\n{state.get('current_answer','')[:6000]}\n\n"
           f"Dangerous ambiguities:\n{_lines([a.get('term') for a in state.get('top_ambiguities', [])])}\n\n"
           f"Meta-question: {meta.get('higher_level_question','')}\n\n"
           f"Skeptic already raised:\n{_lines(state.get('skeptic_output'))}\n\n"
           f"Source Critic already raised:\n{_lines(state.get('source_critic_output'))}\n\n"
           f"Research:\n{_lines([r.get('results') for r in state.get('research', [])], 3)}\n")
    status = "passed"
    try:
        res = call_claude(model=model_for_role("challenge_generation"),
                          system=load_prompt("albert_persona") + "\n\n" + load_prompt("challenge_generation"),
                          user=ctx, json_schema=schemas.CHALLENGE_GENERATION, purpose="challenge_generation")
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_2 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = _stub(), "failed"
    challenges = res.get("albert_challenges") or []
    if not challenges:
        res, status, challenges = _stub(), "failed", _stub()["albert_challenges"]
    state["albert_challenges"] = challenges
    state["weak_points"] = res.get("weak_points") or []
    state["missing_business_context"] = res.get("missing_business_context") or []
    state["would_survive_leadership"] = bool(res.get("would_survive_leadership", False))
    # Ambiguity-hunt folded in (v3.2): take top_ambiguities from the result that
    # returned a non-empty list; if none, pad with a 3-item stub. Always exactly 3.
    amb = res.get("top_ambiguities") or []
    if not isinstance(amb, list) or len(amb) < 3:
        amb = (amb if isinstance(amb, list) else []) + _amb_stub()
    state["top_ambiguities"] = amb[:3]
    state["phase_2_status"], state["phase_2_complete"] = status, True
    _round = state.get("phase_3_attempt_count", 0)
    _label = f"Round {_round + 1} (rework)" if _round else ""
    deliberation.block("phase_2_challenge_generation", "Phase 2 — Challenge generation",
                       deliberation.render_challenges(state, _label))
    return state
