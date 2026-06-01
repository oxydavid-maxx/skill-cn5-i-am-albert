"""Phase 2 (bones 2-11): generate albert_challenges against the current answer, building on
the Skeptic + Source Critic output. Rework loop feeds prior addressable sharpenings back.

Fanned out by generator: one parallel Claude call per generator in GENERATORS (each
focuses on its own bones), then a deterministic merge concatenates the slices."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.parallel import parallel_run
from albert.utils import load_prompt
from albert.state import GENERATORS
from albert import schemas


def _stub(generator="winning"):
    return {"albert_challenges": [{"challenge": "(LLM unavailable — re-run Albert)",
            "why_albert_would_ask": "n/a", "status": "blocked", "severity": "high",
            "current_answer_strength": "weak", "generator": generator, "bone": 2}],
            "weak_points": [], "missing_business_context": [], "would_survive_leadership": False}


def _prior_sharpenings(state):
    rounds = state.get("phase_3_rounds") or []
    if not rounds:
        return ""
    fixes = [w.get("suggested_sharpening", "") for w in rounds[-1].get("weaknesses", [])
             if isinstance(w, dict) and w.get("classification") == "addressable" and w.get("suggested_sharpening")]
    return ("Prior audit said these were too weak — sharpen them:\n" + "\n".join(f"- {f}" for f in fixes) + "\n\n") if fixes else ""


def _lines(items, n=4):
    return "\n".join(f"- {str(i)[:200]}" for i in (items or [])[:n])


def _base_ctx(state):
    meta = state.get("meta_question") or {}
    return (f"{_prior_sharpenings(state)}"
            f"Output purpose: {state.get('output_purpose','')}\n\n"
            f"Current answer:\n{state.get('current_answer','')[:6000]}\n\n"
            f"Dangerous ambiguities:\n{_lines([a.get('term') for a in state.get('top_ambiguities', [])])}\n\n"
            f"Meta-question: {meta.get('higher_level_question','')}\n\n"
            f"Skeptic already raised:\n{_lines(state.get('skeptic_output'))}\n\n"
            f"Source Critic already raised:\n{_lines(state.get('source_critic_output'))}\n\n"
            f"Research:\n{_lines([r.get('results') for r in state.get('research', [])], 3)}\n")


def _focus_line(generator):
    return (f"\nFOCUS: produce ONLY challenges for the '{generator}' generator (its bones). "
            f"2-4 sharp challenges; concise meeting_ready_response and recommended_probe "
            f"(1-2 sentences each).\n")


_SENTINEL = object()


def _call_one(generator, system, ctx):
    """Run one generator's call. Returns the slice dict, or _SENTINEL on (non-contract) failure."""
    try:
        return call_claude(model=model_for_role("challenge_generation"),
                           system=system, user=ctx + _focus_line(generator),
                           json_schema=schemas.CHALLENGE_GENERATION,
                           purpose=f"challenge_generation_{generator}")
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_2 generator '{generator}' failed: "
                         f"{type(e).__name__}: {str(e)[:200]}; skipping\n")
        return _SENTINEL


def _merge(results):
    """Concatenate albert_challenges / weak_points / missing_business_context across slices;
    AND-fold would_survive_leadership (any False => False)."""
    challenges, weak, missing = [], [], []
    survive = True
    for r in results:
        challenges.extend(r.get("albert_challenges") or [])
        weak.extend(r.get("weak_points") or [])
        missing.extend(r.get("missing_business_context") or [])
        survive = survive and bool(r.get("would_survive_leadership", False))
    return {"albert_challenges": challenges, "weak_points": weak,
            "missing_business_context": missing, "would_survive_leadership": survive}


def phase_2_challenge_generation(state: dict) -> dict:
    ctx = _base_ctx(state)
    system = load_prompt("albert_persona") + "\n\n" + load_prompt("challenge_generation")

    tasks = [(lambda g=g: _call_one(g, system, ctx)) for g in GENERATORS]
    raw = parallel_run(tasks)

    # Pair each result with its generator; treat sentinel/empty-challenge slices as failures.
    good, failed = [], []
    for g, r in zip(GENERATORS, raw):
        if r is _SENTINEL or not (isinstance(r, dict) and (r.get("albert_challenges") or [])):
            failed.append(g)
        else:
            good.append(r)

    if not good:
        # ALL slices fell back -> degraded. Keep the existing stub shape.
        sys.stderr.write("[WARN] phase_2: all generators failed; stub\n")
        merged = _merge([_stub(g) for g in GENERATORS])
        status = "failed"
    else:
        for g in failed:
            sys.stderr.write(f"[WARN] phase_2: generator '{g}' produced no slice; proceeding without it\n")
        merged = _merge(good)
        status = "passed"

    state["albert_challenges"] = merged["albert_challenges"]
    state["weak_points"] = merged["weak_points"]
    state["missing_business_context"] = merged["missing_business_context"]
    state["would_survive_leadership"] = bool(merged["would_survive_leadership"])
    state["phase_2_status"], state["phase_2_complete"] = status, True
    return state
