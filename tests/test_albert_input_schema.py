# tests/test_albert_input_schema.py
import json
from pathlib import Path
from albert import schemas
ROOT = Path(__file__).parent.parent

def test_required_and_enriched():
    p = schemas.ALBERT_INPUT["properties"]
    assert set(schemas.ALBERT_INPUT["required"]) >= {"current_answer", "mode"}
    for k in ("meeting_context", "output_purpose", "readiness_scores",
              "recent_research_actions", "skeptic_output", "source_critic_output", "research_state"):
        assert k in p

def test_disk_matches(tmp_path):
    disk = json.loads((ROOT/"schemas"/"albert_input.schema.json").read_text(encoding="utf-8"))
    assert set(disk["properties"]) == set(schemas.ALBERT_INPUT["properties"])
