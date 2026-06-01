# tests/test_websearch_max_turns.py
import albert.sdk_client as sc


def test_default_max_turns(monkeypatch):
    monkeypatch.delenv("ALBERT_WEBSEARCH_MAX_TURNS", raising=False)
    assert sc._websearch_max_turns() == 3


def test_env_override(monkeypatch):
    monkeypatch.setenv("ALBERT_WEBSEARCH_MAX_TURNS", "2")
    assert sc._websearch_max_turns() == 2


def test_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("ALBERT_WEBSEARCH_MAX_TURNS", "xx")
    assert sc._websearch_max_turns() == 3


def test_clamps_to_at_least_one(monkeypatch):
    monkeypatch.setenv("ALBERT_WEBSEARCH_MAX_TURNS", "0")
    assert sc._websearch_max_turns() == 1
