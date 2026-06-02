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
