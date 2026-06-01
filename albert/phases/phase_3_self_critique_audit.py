"""Phase 3: MULTI-VOTE adversarial self-critique (N=3). A challenge is ADDRESSABLE only
when >=2 of 3 votes agree — avoids the self-critique paradox where a single same-model
critic hallucinates flaws (spec §5). A degraded run (all votes failed) may not drive rework."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import ClaudeSession
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas

NUM_VOTES = 3


def _has_addressable(audit: dict) -> bool:
    return any(isinstance(w, dict) and w.get("classification") == "addressable"
               for w in (audit.get("weaknesses") or []))


def phase_3_self_critique_audit(state: dict) -> dict:
    state.setdefault("phase_3_rounds", [])
    payload = json.dumps(state["albert_challenges"], ensure_ascii=False)[:20000]
    votes, fail_count = [], 0
    with ClaudeSession(system=load_prompt("self_critique_auditor"),
                       model=model_for_role("self_critique_audit"),
                       schema=schemas.SELF_CRITIQUE_AUDIT, allow_tools=True,
                       max_turns=3, timeout_sec=240) as sess:
        for v in range(1, NUM_VOTES + 1):
            user = (f"Vote {v} of {NUM_VOTES}. Audit these challenges from a fresh, skeptical angle; "
                    f"classify weaknesses; give a verdict.\n\n{payload}\n\n"
                    "Use WebSearch to check whether a challenge is research-backed.")
            try:
                a = sess.ask(user, purpose=f"self_critique_audit_vote_{v}")
                if isinstance(a, list):
                    a = a[0] if (len(a) == 1 and isinstance(a[0], dict)) else {"weaknesses": a, "verdict": "exhausted"}
                if not isinstance(a, dict):
                    a = {"weaknesses": [], "verdict": "exhausted", "_fallback": True}; fail_count += 1
            except VisibilityContractError:
                raise
            except Exception as e:
                sys.stderr.write(f"[WARN] phase_3 vote {v} failed: {type(e).__name__}: {str(e)[:150]}\n")
                a = {"weaknesses": [], "verdict": "exhausted", "_fallback": True}; fail_count += 1
            votes.append(a)

    state["phase_3_rounds"].append({"votes": votes})
    is_degraded = fail_count >= NUM_VOTES                      # all votes failed -> degraded
    addressable_votes = sum(1 for a in votes if not a.get("_fallback") and _has_addressable(a))
    # Majority of real votes say addressable -> REWORK; else EXHAUSTED. Degraded -> never rework.
    verdict = "REWORK" if (not is_degraded and addressable_votes >= 2) else "EXHAUSTED"
    state["phase_3_verdict"] = verdict
    state["phase_3_status"] = "failed" if is_degraded else "passed"
    state["phase_3_attempt_count"] = state.get("phase_3_attempt_count", 0) + 1
    # Carry the union of addressable sharpenings (from real votes) for phase 2 rework feedback.
    merged = [w for a in votes if not a.get("_fallback")
              for w in (a.get("weaknesses") or []) if w.get("classification") == "addressable"]
    state["phase_3_rounds"][-1]["weaknesses"] = merged
    state["phase_3_complete"] = True
    return state
