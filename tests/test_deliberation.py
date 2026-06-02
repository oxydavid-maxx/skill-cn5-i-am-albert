import pytest
from pathlib import Path
from albert import deliberation
from albert.errors import VisibilityContractError


def test_block_writes_file_and_stderr(tmp_path, capsys):
    deliberation.init(tmp_path)
    deliberation.block("phase_2_challenge_generation", "ignored-title", "卡片內容XYZ")
    md = (tmp_path / "deliberation.md").read_text(encoding="utf-8")
    assert "卡片內容XYZ" in md
    assert "##" not in md  # no markdown heading
    err = capsys.readouterr().err
    assert "卡片內容XYZ" in err


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


def test_render_research_zh():
    state = {"research": [{"query": "TC4 roadmap", "results": "AURIX TC4 targets high-end ZCU ...\n more"}]}
    out = D.render_research(state)
    assert "PHASE 0" in out and "TC4 roadmap" in out
    assert "##" not in out and "**" not in out


def test_render_challenges_zh_cards():
    state = {"top_ambiguities": [{"term": "mid-tier", "why_dangerous": "未定義", "precise_question": "哪個 OEM?"}],
             "albert_challenges": [{"bone": 3, "challenge": "客戶是誰?", "why_albert_would_ask": "無 named socket",
                                    "severity": "high", "current_answer_strength": "weak"}]}
    out = D.render_challenges(state)
    assert "PHASE 2" in out
    assert "拷問" in out
    assert "骨#3" in out
    assert "嚴重度:高" in out and "現答:弱" in out
    assert "客戶是誰?" in out
    assert "┌─ [1/1]" in out
    assert "##" not in out and "**" not in out


def test_render_self_critique_zh():
    votes = [
        {"weaknesses": [{"classification": "addressable", "issue": "無量", "suggested_sharpening": "給 SOP"}], "verdict": "rework"},
        {"weaknesses": [{"classification": "residual", "issue": "總經風險"}], "verdict": "exhausted"},
        {"weaknesses": [{"classification": "addressable", "issue": "無量", "suggested_sharpening": "給 SOP"}], "verdict": "rework"},
    ]
    assessment = {"addressable_votes": 2, "degraded": False, "merged": []}
    out = D.render_self_critique(votes, assessment, "REWORK")
    assert "PHASE 3" in out
    assert "第 1 票" in out and "第 2 票" in out and "第 3 票" in out
    assert "可解決" in out and "殘留" in out
    assert "無量" in out and "磨利:給 SOP" in out
    assert "可解決票 = 2 / 3 → REWORK" in out
    assert "##" not in out and "**" not in out


def test_render_self_critique_degraded_zh():
    votes = [{"weaknesses": [], "verdict": "exhausted", "_fallback": True}]
    assessment = {"addressable_votes": 0, "degraded": True, "merged": []}
    out = D.render_self_critique(votes, assessment, "EXHAUSTED")
    assert "degraded" in out.lower()


def test_render_rework_zh():
    merged = [{"issue": "無量", "suggested_sharpening": "給 SOP window"}]
    out = D.render_rework(2, merged)
    assert "Round 2" in out
    assert "給 SOP window" in out


def test_render_signals_zh():
    merged = {"premature_end_risk": {"level": "high", "why": "6 條未解"},
              "research_drift_risk": {"level": "low", "why": "在原集合"},
              "proposed_next_action": "pull_human", "recommended_next_action": "pull_human"}
    out = D.render_signals(merged)
    assert "PHASE 4" in out
    assert "提前結束風險:高 — 6 條未解" in out
    assert "研究偏移風險:低 — 在原集合" in out
    assert "pull_human" in out
    assert "##" not in out and "**" not in out


def test_render_verdict_zh():
    final = {"verdict_standalone": "要補證據", "light": "red", "readiness_score_delta": 1,
             "recommended_next_action": "pull_human", "reproducible_judgment": "方向對但證據不足"}
    out = D.render_verdict(final)
    assert "PHASE 5" in out
    assert "判定:要補證據" in out
    assert "🔴" in out
    assert "準備度變化:1" in out
    assert "方向對但證據不足" in out
    assert "##" not in out and "**" not in out
