import pytest
from albert import deliberation
from albert.graph import _wrap
from albert.errors import VisibilityContractError


def test_wrap_fails_closed_when_phase_silent(tmp_path):
    deliberation.init(tmp_path)

    def silent_phase(state):
        return {"ok": True}

    wrapped = _wrap("phase_2_challenge_generation", silent_phase)
    with pytest.raises(VisibilityContractError):
        wrapped({"run_dir": str(tmp_path)})


def test_wrap_passes_when_phase_emits(tmp_path):
    deliberation.init(tmp_path)

    def good_phase(state):
        deliberation.block("phase_2_challenge_generation", "C", "x")
        return {"ok": True}

    wrapped = _wrap("phase_2_challenge_generation", good_phase)
    result = wrapped({"run_dir": str(tmp_path)})
    assert result["ok"] is True
