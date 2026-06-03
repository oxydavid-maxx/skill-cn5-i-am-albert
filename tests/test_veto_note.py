from albert import deliberation
from albert.phases import phase_4_signals_action_gate as p4


def _run_with(monkeypatch, tmp_path, res):
    deliberation.init(tmp_path)
    monkeypatch.setattr(p4, "call_claude", lambda **k: res)
    state = {"current_answer": "x", "albert_challenges": [], "research_state": {}}
    return p4.phase_4_signals_action_gate(state)


def test_note_appended_when_vetoed(tmp_path, monkeypatch):
    res = {"premature_end_atoms": {"open_high_impact_challenges": 3, "new_info_rate": "high"},
           "drift_atoms": {}, "proposed_next_action": "synthesize",
           "reproducible_judgment": "建議 synthesize。",
           "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []}}
    state = _run_with(monkeypatch, tmp_path, res)
    assert state["recommended_next_action"] == "continue_research"
    assert "經訊號否決改為 continue_research" in state["reproducible_judgment"]
    assert "synthesize" in state["reproducible_judgment"]


def test_no_note_when_not_vetoed(tmp_path, monkeypatch):
    res = {"premature_end_atoms": {"open_high_impact_challenges": 0, "new_info_rate": "low",
           "challenge_map_mostly_classified": True, "unresolved_are_human_data_decision_only": True},
           "drift_atoms": {"current_focus_in_original_high_value_set": True, "high_value_branch_ignored": False},
           "proposed_next_action": "synthesize", "reproducible_judgment": "建議 synthesize。",
           "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []}}
    state = _run_with(monkeypatch, tmp_path, res)
    assert state["recommended_next_action"] == "synthesize"
    assert "經訊號否決" not in state["reproducible_judgment"]
