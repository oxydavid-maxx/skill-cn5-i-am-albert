import pytest
from pathlib import Path
from albert import deliberation
from albert.errors import VisibilityContractError


def test_block_writes_file_and_stderr(tmp_path, capsys):
    deliberation.init(tmp_path)
    deliberation.block("phase_2_challenge_generation", "Challenges", "bone #1 · why · what")
    md = (tmp_path / "deliberation.md").read_text(encoding="utf-8")
    assert "Challenges" in md
    assert "bone #1" in md
    err = capsys.readouterr().err
    assert "DELIBERATION" in err
    assert "bone #1" in err


def test_emitted_tracks_phases(tmp_path):
    deliberation.init(tmp_path)
    assert deliberation.emitted("phase_3_self_critique_audit") is False
    deliberation.block("phase_3_self_critique_audit", "Self-critique", "vote 1 ...")
    assert deliberation.emitted("phase_3_self_critique_audit") is True


def test_assert_emitted_raises_when_silent(tmp_path):
    deliberation.init(tmp_path)
    with pytest.raises(VisibilityContractError):
        deliberation.assert_emitted("phase_4_signals_action_gate")


def test_assert_emitted_passes_after_block(tmp_path):
    deliberation.init(tmp_path)
    deliberation.block("phase_4_signals_action_gate", "Signals", "premature-end: low")
    deliberation.assert_emitted("phase_4_signals_action_gate")


def test_init_resets_emitted_set(tmp_path):
    deliberation.init(tmp_path)
    deliberation.block("phase_2_challenge_generation", "C", "x")
    deliberation.init(tmp_path)
    assert deliberation.emitted("phase_2_challenge_generation") is False


def test_block_raises_when_dir_unwritable(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    monkeypatch.setattr(deliberation, "_path", tmp_path / "nonexistent-subdir" / "deliberation.md")
    with pytest.raises(VisibilityContractError):
        deliberation.block("phase_2_challenge_generation", "C", "x")


from albert import deliberation as D


def test_render_research():
    state = {"research": [{"query": "TC4 gateway socket size", "results": "AURIX TC4 targets high-end ZCU ..."}]}
    out = D.render_research(state)
    assert "TC4 gateway socket size" in out
    assert "AURIX TC4" in out


def test_render_challenges():
    state = {"top_ambiguities": [{"term": "mid-tier", "why_dangerous": "undefined", "precise_question": "which OEM?"}],
             "albert_challenges": [{"bone": 3, "challenge": "Who is the customer?",
                                    "why_albert_would_ask": "no named socket", "severity": "high",
                                    "current_answer_strength": "weak"}]}
    out = D.render_challenges(state)
    assert "mid-tier" in out
    assert "bone #3" in out
    assert "Who is the customer?" in out
    assert "high" in out


def test_render_self_critique_debate():
    votes = [
        {"weaknesses": [{"classification": "addressable", "issue": "no volume", "suggested_sharpening": "name SOP"}], "verdict": "rework"},
        {"weaknesses": [{"classification": "residual", "issue": "macro risk"}], "verdict": "exhausted"},
        {"weaknesses": [{"classification": "addressable", "issue": "no volume", "suggested_sharpening": "name SOP"}], "verdict": "rework"},
    ]
    assessment = {"addressable_votes": 2, "degraded": False, "merged": []}
    out = D.render_self_critique(votes, assessment, "REWORK")
    assert "Vote 1" in out and "Vote 2" in out and "Vote 3" in out
    assert "no volume" in out
    assert "2" in out
    assert "REWORK" in out


def test_render_self_critique_degraded():
    votes = [{"weaknesses": [], "verdict": "exhausted", "_fallback": True}]
    assessment = {"addressable_votes": 0, "degraded": True, "merged": []}
    out = D.render_self_critique(votes, assessment, "EXHAUSTED")
    assert "degraded" in out.lower()


def test_render_rework():
    merged = [{"issue": "no volume", "suggested_sharpening": "name the SOP window"}]
    out = D.render_rework(2, merged)
    assert "Round 2" in out
    assert "name the SOP window" in out


def test_render_signals():
    merged = {"premature_end_risk": {"level": "low", "why": "all high-impact open"},
              "research_drift_risk": {"level": "medium", "why": "off original set"},
              "proposed_next_action": "continue_research", "recommended_next_action": "continue_research"}
    out = D.render_signals(merged)
    assert "premature" in out.lower()
    assert "low" in out
    assert "continue_research" in out


def test_render_verdict():
    final = {"verdict_standalone": "要補證據", "light": "yellow",
             "readiness_score_delta": -1, "recommended_next_action": "continue_research",
             "reproducible_judgment": "weak on named socket"}
    out = D.render_verdict(final)
    assert "yellow" in out
    assert "-1" in out
    assert "weak on named socket" in out
