from pathlib import Path
from albert import deliberation


def test_phase_2_emits_block(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    from albert.phases import phase_2_challenge_generation as p2
    monkeypatch.setattr(p2, "call_claude", lambda **k: {
        "albert_challenges": [{"bone": 1, "challenge": "c", "why_albert_would_ask": "w",
                               "severity": "high", "current_answer_strength": "weak",
                               "generator": "winning", "status": "needs_bu_judgment"}],
        "weak_points": ["wp"], "would_survive_leadership": False,
        "top_ambiguities": [{"term": "t", "why_dangerous": "d", "precise_question": "q"}]})
    state = {"current_answer": "x", "albert_input": {"current_answer": "x", "mode": "standalone"}}
    p2.phase_2_challenge_generation(state)
    assert deliberation.emitted("phase_2_challenge_generation")
    assert "骨#1" in (tmp_path / "deliberation.md").read_text(encoding="utf-8")


def test_phase_3_emits_debate(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    from albert.phases import phase_3_self_critique_audit as p3
    monkeypatch.setattr(p3, "_one_vote", lambda v, payload, digest: {
        "weaknesses": [{"classification": "addressable", "issue": "no volume", "suggested_sharpening": "name SOP"}],
        "verdict": "rework"})
    state = {"albert_challenges": [{"challenge": "c"}], "research": []}
    p3.phase_3_self_critique_audit(state)
    assert deliberation.emitted("phase_3_self_critique_audit")
    md = (tmp_path / "deliberation.md").read_text(encoding="utf-8")
    assert "第 1 票" in md and "no volume" in md
