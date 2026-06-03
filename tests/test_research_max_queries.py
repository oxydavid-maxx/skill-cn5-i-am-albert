import importlib
p0 = importlib.import_module("albert.phases.phase_0_intake_grounding")


def test_default_is_eight(monkeypatch):
    monkeypatch.delenv("ALBERT_RESEARCH_MAX_QUERIES", raising=False)
    assert p0._research_max_queries() == 8


def test_env_caps(monkeypatch):
    monkeypatch.setenv("ALBERT_RESEARCH_MAX_QUERIES", "3")
    assert p0._research_max_queries() == 3


def test_bad_value(monkeypatch):
    monkeypatch.setenv("ALBERT_RESEARCH_MAX_QUERIES", "x")
    assert p0._research_max_queries() == 8
