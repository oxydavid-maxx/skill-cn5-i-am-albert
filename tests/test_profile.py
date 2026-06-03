from albert.profile import resolve_profile, apply_profile, FAST_DEFAULTS


def test_resolve_flag_wins():
    assert resolve_profile(True, {}) == "fast"


def test_resolve_env_when_no_flag():
    assert resolve_profile(False, {"ALBERT_PROFILE": "fast"}) == "fast"
    assert resolve_profile(False, {"ALBERT_PROFILE": "FAST"}) == "fast"


def test_resolve_default_thorough():
    assert resolve_profile(False, {}) == "thorough"
    assert resolve_profile(False, {"ALBERT_PROFILE": ""}) == "thorough"


def test_apply_fast_sets_defaults_on_empty_env():
    env = {}
    applied = apply_profile("fast", env)
    assert env["ALBERT_MAX_REWORK"] == "0"
    assert env["ALBERT_WEBSEARCH_MAX_TURNS"] == "3"
    assert env["ALBERT_RESEARCH_WIDTH"] == "5"
    assert applied == dict(FAST_DEFAULTS)


def test_apply_fast_never_clobbers_explicit_env():
    env = {"ALBERT_MAX_REWORK": "2"}
    apply_profile("fast", env)
    assert env["ALBERT_MAX_REWORK"] == "2"
    assert env["ALBERT_WEBSEARCH_MAX_TURNS"] == "3"


def test_apply_thorough_is_noop():
    env = {}
    assert apply_profile("thorough", env) == {}
    assert env == {}
