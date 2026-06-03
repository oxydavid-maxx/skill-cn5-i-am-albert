from albert.graph import _route_after_intake


def test_route_quick():
    assert _route_after_intake({"profile": "quick"}) == "phase_quick_combined"


def test_route_default():
    assert _route_after_intake({"profile": "thorough"}) == "phase_2_challenge_generation"
    assert _route_after_intake({}) == "phase_2_challenge_generation"
