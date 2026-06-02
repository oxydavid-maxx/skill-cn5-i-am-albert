"""Phase 3: MULTI-VOTE adversarial self-critique (N=3). A challenge is ADDRESSABLE only
when >=2 of 3 votes agree — avoids the self-critique paradox where a single same-model
critic hallucinates flaws (spec §5). A degraded run (all votes failed) may not drive rework.

The 3 votes are INDEPENDENT (each is a fresh, stateless audit from a skeptical angle), so
they fan out as 3 parallel call_claude calls. The aggregate + convergence rule are pulled
out into pure helpers (`_aggregate_votes`, `_converged`) so the convergence logic is a clean
seam for a future shared converge engine."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.parallel import parallel_run
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert import deliberation

NUM_VOTES = 3


def _has_addressable(audit: dict) -> bool:
    return any(isinstance(w, dict) and w.get("classification") == "addressable"
               for w in (audit.get("weaknesses") or []))


def _aggregate_votes(votes: list) -> dict:
    """Pure aggregation over the N collected vote dicts.

    Returns:
      addressable_votes - count of REAL (non-fallback) votes that flag an addressable weakness
      degraded          - True iff EVERY vote fell back (all votes failed)
      merged            - union of addressable weaknesses across real votes (for rework feedback)
    """
    degraded = len(votes) > 0 and all(a.get("_fallback") for a in votes)
    addressable_votes = sum(1 for a in votes
                            if not a.get("_fallback") and _has_addressable(a))
    merged = [w for a in votes if not a.get("_fallback")
              for w in (a.get("weaknesses") or []) if w.get("classification") == "addressable"]
    return {"addressable_votes": addressable_votes, "degraded": degraded, "merged": merged}


def _converged(assessment: dict) -> str:
    """Pure convergence rule: REWORK iff a non-degraded run has majority-addressable votes.

    Majority of real votes say addressable -> REWORK; else EXHAUSTED. A degraded
    run (all votes failed) never drives rework."""
    if not assessment["degraded"] and assessment["addressable_votes"] >= 2:
        return "REWORK"
    return "EXHAUSTED"


def _one_vote(v: int, payload: str, digest: str) -> dict:
    """Run a single independent audit vote as a stateless call. Returns the
    audit dict, or a _fallback stub on (non-visibility) failure.

    The vote judges 'research-backed' against the research already gathered in
    state (passed in as ``digest``); it does NOT re-search the web."""
    user = (f"Vote {v} of {NUM_VOTES}. Audit these challenges from a fresh, skeptical angle; "
            f"classify each weakness; give a verdict.\n\nChallenges:\n{payload}\n\n"
            f"Research already gathered (judge 'research-backed' against THIS, do not search):\n{digest}\n")
    try:
        a = call_claude(model=model_for_role("self_critique_audit"),
                        system=load_prompt("self_critique_auditor"),
                        user=user, json_schema=schemas.SELF_CRITIQUE_AUDIT,
                        allow_tools=False, timeout_sec=240,
                        purpose=f"self_critique_audit_vote_{v}")
        if isinstance(a, list):
            a = a[0] if (len(a) == 1 and isinstance(a[0], dict)) else {"weaknesses": a, "verdict": "exhausted"}
        if not isinstance(a, dict):
            return {"weaknesses": [], "verdict": "exhausted", "_fallback": True}
        return a
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_3 vote {v} failed: {type(e).__name__}: {str(e)[:150]}\n")
        return {"weaknesses": [], "verdict": "exhausted", "_fallback": True}


def phase_3_self_critique_audit(state: dict) -> dict:
    state.setdefault("phase_3_rounds", [])
    payload = json.dumps(state["albert_challenges"], ensure_ascii=False)[:20000]

    # Build a digest of the research already gathered ONCE; each vote judges
    # 'research-backed' against this instead of re-searching the web.
    research = state.get("research") or []
    digest = "\n".join(f"- {r.get('query','')}: {str(r.get('results',''))[:300]}" for r in research[:6])

    # The 3 votes are independent -> fan out as parallel stateless calls.
    # VisibilityContractError from any vote propagates through parallel_run.result()
    # and aborts the phase.
    votes = parallel_run([
        (lambda v=v: _one_vote(v, payload, digest)) for v in range(1, NUM_VOTES + 1)
    ])

    state["phase_3_rounds"].append({"votes": votes})

    assessment = _aggregate_votes(votes)
    verdict = _converged(assessment)
    state["phase_3_verdict"] = verdict
    state["phase_3_status"] = "failed" if assessment["degraded"] else "passed"
    state["phase_3_attempt_count"] = state.get("phase_3_attempt_count", 0) + 1
    # Carry the union of addressable sharpenings (from real votes) for phase 2 rework feedback.
    state["phase_3_rounds"][-1]["weaknesses"] = assessment["merged"]
    deliberation.block("phase_3_self_critique_audit", "Phase 3 — Self-critique debate",
                       deliberation.render_self_critique(votes, assessment, verdict))
    if verdict == "REWORK":
        deliberation.block("phase_3_self_critique_audit", "Rework decision",
                           deliberation.render_rework(state["phase_3_attempt_count"], assessment["merged"]))
    state["phase_3_complete"] = True
    return state
