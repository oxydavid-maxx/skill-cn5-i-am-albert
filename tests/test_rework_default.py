import importlib
run_albert = importlib.import_module("run_albert")


def test_standalone_sets_default_when_unset():
    env = {}
    run_albert._apply_standalone_rework_default("standalone", env)
    assert env["ALBERT_MAX_REWORK"] == "1"


def test_standalone_respects_explicit_env():
    env = {"ALBERT_MAX_REWORK": "3"}
    run_albert._apply_standalone_rework_default("standalone", env)
    assert env["ALBERT_MAX_REWORK"] == "3"


def test_cockpit_unchanged():
    env = {}
    run_albert._apply_standalone_rework_default("cockpit", env)
    assert "ALBERT_MAX_REWORK" not in env
