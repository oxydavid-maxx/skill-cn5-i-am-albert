from albert import schemas


def test_quick_combined_has_challenge_and_verdict_fields():
    props = schemas.QUICK_COMBINED["properties"]
    assert "albert_challenges" in props
    assert "top_ambiguities" in props
    assert "premature_end_atoms" in props
    assert "verdict_standalone" in props
    assert "proposed_next_action" in props
    assert schemas.QUICK_COMBINED["type"] == "object"
