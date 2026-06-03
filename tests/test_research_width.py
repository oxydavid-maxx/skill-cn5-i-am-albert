import importlib
p0 = importlib.import_module("albert.phases.phase_0_intake_grounding")


def test_research_width_default(monkeypatch):
    monkeypatch.delenv("ALBERT_RESEARCH_WIDTH", raising=False)
    assert p0._research_width() == 3


def test_research_width_env(monkeypatch):
    monkeypatch.setenv("ALBERT_RESEARCH_WIDTH", "5")
    assert p0._research_width() == 5


def test_research_width_bad_value(monkeypatch):
    monkeypatch.setenv("ALBERT_RESEARCH_WIDTH", "notint")
    assert p0._research_width() == 3
