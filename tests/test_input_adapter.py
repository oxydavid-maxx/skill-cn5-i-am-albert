# tests/test_input_adapter.py
from albert.input_adapter import build_input

def test_text_standalone_synth_current_answer():
    inp = build_input(raw_text="Build a zonal controller. No spec.", input_json=None)
    assert inp["mode"] == "standalone"
    assert "zonal controller" in inp["current_answer"]
    assert inp["research_state"] == {} and inp["readiness_scores"] == {}

def test_json_cockpit_passthrough(tmp_path):
    import json
    p = tmp_path/"in.json"
    p.write_text(json.dumps({"current_answer": "x", "mode": "cockpit",
        "research_state": {"new_info_rate": "low"}, "readiness_scores": {"decision_readiness": 3}}), encoding="utf-8")
    inp = build_input(raw_text=None, input_json=str(p))
    assert inp["mode"] == "cockpit" and inp["readiness_scores"]["decision_readiness"] == 3
