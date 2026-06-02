from albert.signals import premature_end_why, drift_why, premature_end_level, drift_level


def test_premature_end_why_explains_high():
    atoms = {"new_info_rate": "high", "open_high_impact_challenges": 8,
             "challenge_map_mostly_classified": False,
             "unresolved_are_human_data_decision_only": False,
             "meta_question_search_found_new_high_impact_angle": False}
    assert premature_end_level(atoms) == "high"
    why = premature_end_why(atoms)
    assert why  # non-empty
    assert "8" in why  # mentions the open high-impact count
    # mentions at least one violated condition keyword
    assert ("new_info_rate" in why) or ("new info" in why.lower())


def test_premature_end_why_explains_low():
    atoms = {"new_info_rate": "low", "open_high_impact_challenges": 0,
             "challenge_map_mostly_classified": True,
             "unresolved_are_human_data_decision_only": True,
             "meta_question_search_found_new_high_impact_angle": False}
    assert premature_end_level(atoms) == "low"
    why = premature_end_why(atoms)
    assert why  # non-empty even when low (explains WHY it's safe to stop)


def test_drift_why_explains_levels():
    high_atoms = {"current_focus_in_original_high_value_set": False, "high_value_branch_ignored": True}
    assert drift_level(high_atoms) == "high"
    assert drift_why(high_atoms)  # non-empty
    low_atoms = {"current_focus_in_original_high_value_set": True, "high_value_branch_ignored": False}
    assert drift_level(low_atoms) == "low"
    assert drift_why(low_atoms)  # non-empty


def test_build_risk_carries_why():
    from albert.signals import build_risk
    r = build_risk("high", {"x": 1}, None, why="because reasons")
    assert r["why"] == "because reasons"
