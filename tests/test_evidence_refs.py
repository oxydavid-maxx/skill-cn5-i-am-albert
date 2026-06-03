from albert.utils import research_refs
from albert import deliberation as D


def test_research_refs_enumerates_with_ids():
    research = [{"query": "TC4 roadmap", "results": "AURIX TC4 targets high-end ZCU\nmore text"},
                {"query": "S32G3 successor", "results": "NXP S32G3 ships now"}]
    out = research_refs(research)
    assert "[R1] TC4 roadmap → AURIX TC4 targets high-end ZCU more text" in out
    assert "[R2] S32G3 successor → NXP S32G3 ships now" in out


def test_research_refs_caps_and_truncates():
    research = [{"query": f"q{i}", "results": "x" * 500} for i in range(12)]
    out = research_refs(research, limit=8, snip=180)
    assert "[R8]" in out and "[R9]" not in out
    assert "x" * 181 not in out


def test_render_challenges_shows_evidence_refs():
    state = {"top_ambiguities": [], "albert_challenges": [
        {"bone": 2, "challenge": "c", "why_albert_would_ask": "w", "severity": "high",
         "current_answer_strength": "weak", "evidence_refs": ["R1", "R3"]}]}
    out = D.render_challenges(state)
    assert "證據:R1, R3" in out


def test_render_challenges_omits_evidence_line_when_empty():
    state = {"top_ambiguities": [], "albert_challenges": [
        {"bone": 2, "challenge": "c", "why_albert_would_ask": "w", "severity": "high",
         "current_answer_strength": "weak", "evidence_refs": []}]}
    out = D.render_challenges(state)
    assert "證據:" not in out
