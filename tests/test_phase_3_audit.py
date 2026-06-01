# tests/test_phase_3_audit.py
import threading

from albert.phases.phase_3_self_critique_audit import phase_3_self_critique_audit


def _patch(mp, votes):
    """Patch call_claude (votes are now independent stateless calls).

    Returns the next queued vote per call; None means that vote raises (transport
    failure, exercised by the all-fail case). Thread-safe because parallel_run
    fans the 3 votes out concurrently."""
    import albert.phases.phase_3_self_critique_audit as m
    state = {"i": 0, "lock": threading.Lock()}
    queue = list(votes)

    def fake_call_claude(**k):
        with state["lock"]:
            v = queue[state["i"] % len(queue)]
            state["i"] += 1
        if v is None:
            raise RuntimeError("transport")
        return v

    mp.setattr(m, "call_claude", fake_call_claude)


def _addr():
    return {"round": 1, "verdict": "rework",
            "weaknesses": [{"challenge_index": 0, "classification": "addressable", "issue": "vague"}]}


def _res():
    return {"round": 1, "verdict": "exhausted",
            "weaknesses": [{"challenge_index": 0, "classification": "residual", "issue": "ask customer"}]}


def test_majority_addressable_is_rework(monkeypatch):
    _patch(monkeypatch, [_addr(), _addr(), _res()])     # 2/3 addressable
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_verdict"] == "REWORK" and out["phase_3_status"] == "passed"
    assert out["phase_3_attempt_count"] == 1


def test_minority_addressable_is_exhausted(monkeypatch):
    _patch(monkeypatch, [_addr(), _res(), _res()])      # only 1/3 addressable
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_verdict"] == "EXHAUSTED"


def test_all_votes_fail_marks_failed_and_exhausted(monkeypatch):
    _patch(monkeypatch, [None, None, None])
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_status"] == "failed" and out["phase_3_verdict"] == "EXHAUSTED"
