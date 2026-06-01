# tests/test_prompts_present.py
import pytest
from albert.utils import load_prompt
NAMES = ["albert_persona","intake_grounding","search_reflection","ambiguity_hunt",
         "challenge_generation","self_critique_auditor","signals_action_gate","verdict_render"]

@pytest.mark.parametrize("n", NAMES)
def test_loads(n): assert len(load_prompt(n)) > 50

def test_persona_twelve_bones():
    t = load_prompt("albert_persona")
    for n in range(1, 13): assert f"{n}." in t

def test_persona_durability():
    assert "durab" in load_prompt("albert_persona").lower() or "moat" in load_prompt("albert_persona").lower()

def test_auditor_adversarial():
    assert "adversarial" in load_prompt("self_critique_auditor").lower()

def test_signals_prompt_demands_atoms_and_action():
    t = load_prompt("signals_action_gate").lower()
    assert "atom" in t and "proposed_next_action" in t and "do not output the final" in t
