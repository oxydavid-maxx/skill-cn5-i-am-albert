from albert.graph import _route_from_start
from albert.state import AlbertState


def test_route_from_start_flash():
    assert _route_from_start({"profile": "flash"}) == "phase_flash"


def test_route_from_start_default():
    assert _route_from_start({"profile": "thorough"}) == "phase_0_intake_grounding"
    assert _route_from_start({}) == "phase_0_intake_grounding"


def test_flash_route_survives_state_filter():
    initial = {"profile": "flash", "mode": "standalone", "_x": 1}
    kept = {k: v for k, v in initial.items() if k in AlbertState.__annotations__}
    assert _route_from_start(kept) == "phase_flash"
