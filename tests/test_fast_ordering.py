import importlib
run_albert = importlib.import_module("run_albert")
from albert.profile import apply_profile


def test_fast_then_standalone_default_keeps_zero():
    env = {}
    apply_profile("fast", env)
    run_albert._apply_standalone_rework_default("standalone", env)
    assert env["ALBERT_MAX_REWORK"] == "0"


def test_thorough_standalone_still_defaults_one():
    env = {}
    apply_profile("thorough", env)
    run_albert._apply_standalone_rework_default("standalone", env)
    assert env["ALBERT_MAX_REWORK"] == "1"
