"""Normalize a raw proposal (standalone) or cockpit input JSON into albert_input."""
import json
from pathlib import Path

_DEFAULTS = {"original_objective": "", "meeting_context": "", "output_purpose": "decision_readiness",
             "issue_map": [], "challenge_map": [], "evidence": [], "skeptic_output": [],
             "source_critic_output": [], "readiness_scores": {}, "recent_research_actions": [],
             "research_state": {}, "proposal": {}}


def build_input(raw_text: str | None, input_json: str | None) -> dict:
    if input_json:
        data = json.loads(Path(input_json).read_text(encoding="utf-8"))
        data.setdefault("mode", "cockpit")
        data.setdefault("current_answer", "")
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v.copy() if isinstance(v, (dict, list)) else v)
        return data
    body = raw_text or ""
    p = Path(body)
    if len(body) < 400 and p.exists() and p.is_file():
        body = p.read_text(encoding="utf-8")
    title = body.strip().splitlines()[0][:120] if body.strip() else "(untitled proposal)"
    data = {"mode": "standalone", "current_answer": body}
    for k, v in _DEFAULTS.items():
        data[k] = v.copy() if isinstance(v, (dict, list)) else v
    data["proposal"] = {"title": title, "body": body, "domain": ""}
    return data
