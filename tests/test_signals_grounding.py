# tests/test_signals_grounding.py
from albert.signals import premature_end_level, drift_level, rank_next_probe, grounding_of

_STOP_OK = {"open_high_impact_challenges": 0, "new_info_rate": "low",
            "challenge_map_mostly_classified": True, "unresolved_are_human_data_decision_only": True,
            "meta_question_search_found_new_high_impact_angle": False}

def test_all_stop_met_low(): assert premature_end_level(_STOP_OK) == "low"
def test_two_violations_high():
    assert premature_end_level(dict(_STOP_OK, open_high_impact_challenges=2, new_info_rate="high")) == "high"
def test_meta_question_blocks_low():
    assert premature_end_level(dict(_STOP_OK, meta_question_search_found_new_high_impact_angle=True)) != "low"
def test_drift_low():
    assert drift_level({"current_focus_in_original_high_value_set": True, "high_value_branch_ignored": False}) == "low"
def test_drift_high():
    assert drift_level({"current_focus_in_original_high_value_set": False, "high_value_branch_ignored": True}) == "high"
def test_grounding():
    assert grounding_of({}) == "inferred"
    assert grounding_of({"branches_explored": ["a"]}) == "research_state"
def test_rank():
    r = rank_next_probe([{"probe": "a", "impact": "low", "answerability": "high"},
                         {"probe": "b", "impact": "high", "answerability": "low"}])
    assert r[0]["probe"] == "b" and r[0]["priority"] == 1
