from albert.utils import load_prompt

_USER_VISIBLE = ["albert_persona", "challenge_generation", "self_critique_auditor",
                 "signals_action_gate", "verdict_render", "ambiguity_hunt",
                 "intake_grounding", "search_reflection"]


def test_every_user_visible_prompt_has_zh_directive():
    for name in _USER_VISIBLE:
        text = load_prompt(name)
        assert "繁體中文" in text, f"{name} missing 繁體中文 directive"


def test_persona_no_longer_says_match_the_input():
    assert "match the input" not in load_prompt("albert_persona").lower()
