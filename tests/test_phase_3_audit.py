# tests/test_phase_3_audit.py
from albert.phases.phase_3_self_critique_audit import phase_3_self_critique_audit

class _Sess:
    """Returns the next queued audit per ask() call (one per vote)."""
    def __init__(self, votes): self.votes = list(votes); self.i = 0
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def ask(self, user, purpose="x"):
        v = self.votes[self.i % len(self.votes)]; self.i += 1
        if v is None: raise RuntimeError("transport")
        return v

def _patch(mp, votes):
    import albert.phases.phase_3_self_critique_audit as m
    mp.setattr(m, "ClaudeSession", lambda **k: _Sess(votes))

def _addr(): return {"round": 1, "verdict": "rework", "weaknesses": [{"challenge_index": 0, "classification": "addressable", "issue": "vague"}]}
def _res():  return {"round": 1, "verdict": "exhausted", "weaknesses": [{"challenge_index": 0, "classification": "residual", "issue": "ask customer"}]}

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
