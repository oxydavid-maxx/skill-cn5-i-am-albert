# tests/test_albert_challenge_schema.py
import json, jsonschema
from pathlib import Path
from albert import schemas
ROOT = Path(__file__).parent.parent

def test_auditresult_fields_present():
    props = schemas.ALBERT_CHALLENGE["properties"]
    for k in ("verdict", "albert_challenges", "weak_points", "premature_end_risk",
              "research_drift_risk", "recommended_next_action", "rationale", "degraded"):
        assert k in props

def test_verdict_is_audit_verdict_enum():
    assert schemas.ALBERT_CHALLENGE["properties"]["verdict"]["enum"] == ["continue", "exhausted", "rework"]

def test_recommended_next_action_is_decision_enum():
    assert schemas.ALBERT_CHALLENGE["properties"]["recommended_next_action"]["enum"] == \
        ["continue_research", "branch", "rerank", "pull_human", "push_human",
         "synthesize", "pause", "terminal_stop"]

def test_weak_points_is_list_of_strings():
    assert schemas.ALBERT_CHALLENGE["properties"]["weak_points"]["items"]["type"] == "string"

def test_challenge_entry_has_severity_and_strength():
    entry = schemas.ALBERT_CHALLENGE["properties"]["albert_challenges"]["items"]["properties"]
    assert entry["status"]["enum"][3] == "needs_internal_data"
    assert entry["severity"]["enum"] == ["low", "medium", "high"]
    assert entry["current_answer_strength"]["enum"] == ["weak", "medium", "strong"]

def test_disk_matches_module():
    disk = json.loads((ROOT/"schemas"/"albert_challenge.schema.json").read_text(encoding="utf-8"))
    assert disk["properties"]["verdict"]["enum"] == schemas.ALBERT_CHALLENGE["properties"]["verdict"]["enum"]
