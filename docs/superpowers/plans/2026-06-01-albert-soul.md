# Albert Soul Implementation Plan (v0.4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `skill-cn5-i-am-albert` — a LangGraph FSM **Albert Thought Agent** that audits a *current answer*, returning a contract that maps 1:1 to the cockpit's implemented `AuditResult` (challenges, weak points, rule-grounded stop/drift signals, a recommended next action, rationale, and a `degraded` flag).

**Architecture:** Six-phase `StateGraph` + one conditional edge (Phase 3 self-critique → Phase 2). Loop signals are computed by a deterministic rule engine over named atoms (aligned to consumer §9.3); the recommended next action is LLM-proposed but **vetoed for consistency** with the signals. Phase 3 self-critique is **multi-vote** (N=3, ≥2 agree) to avoid the self-critique paradox. Infra copied from `skill-ai-escape-mrc` (rename `ai_escape_mrc`→`albert`). Dual-mode: cockpit (`albert_input.json` → `albert_challenge.json`) and standalone.

**Tech Stack:** Python 3, `langgraph`, `langgraph-checkpoint-sqlite`, `claude-agent-sdk`, `tenacity`, `pytest`, `jsonschema`.

**Spec:** `docs/superpowers/specs/2026-06-01-albert-soul-design.md` (v0.4.1).
**Reference sibling (read-only):** `D:/D-claude/skills/skill-ai-escape-mrc/`
**Frozen cockpit enums (from `skill-cn5-research-cos/docs/superpowers/plans/2026-06-01-phase1-implementation-plan.md`):**
`AuditVerdict = continue|exhausted|rework` · `Decision = continue_research|branch|rerank|pull_human|push_human|synthesize|pause|terminal_stop` · `Risk = low|medium|high` · `Classification = addressable|residual` · `ChallengeStatus` = the 8 values below.

---

## File Structure

```
skill-cn5-i-am-albert/
  SKILL.md README.md requirements.txt run_albert.py
  albert/
    __init__.py
    no_console.py errors.py utils.py progress.py heartbeat.py stage_summary.py sdk_client.py  (COPY)
    models.py state.py schemas.py signals.py render.py email_delivery.py
    input_adapter.py cockpit_contract.py graph.py
    prompts/ albert_persona.txt intake_grounding.txt search_reflection.txt ambiguity_hunt.txt
             challenge_generation.txt self_critique_auditor.txt signals_action_gate.txt verdict_render.txt
    phases/ phase_0_intake_grounding.py phase_1_ambiguity_hunt.py phase_2_challenge_generation.py
            phase_3_self_critique_audit.py phase_4_signals_action_gate.py phase_5_assemble_render.py
  schemas/ albert_input.schema.json albert_challenge.schema.json
  templates/ albert_report_template.md
  docs/ albert-cockpit-mapping.md albert-reviews/ superpowers/specs/2026-06-01-albert-soul-design.md
  tests/ test_models_routing.py test_state_shape.py test_albert_input_schema.py
         test_albert_challenge_schema.py test_signals_grounding.py test_action_consistency.py
         test_prompts_present.py test_input_adapter.py test_phase_0_intake.py test_phase_1_ambiguity.py
         test_phase_2_challenge.py test_phase_3_audit.py test_phase_4_signals.py test_phase_5_assemble.py
         test_render_degraded_guard.py test_cockpit_contract.py test_email_delivery.py
         test_graph_topology.py test_self_critique_loop.py
```

**Phase convention:** `def phase_x(state: dict) -> dict:`; LLM via `call_claude(...)` / `ClaudeSession`; `load_prompt("x")` reads `albert/prompts/x.txt`; every LLM phase has a stub fallback and sets `phase_x_status` ∈ passed/failed.

---

## Task 1: Scaffold + copy infra

**Files:** `albert/__init__.py`, `albert/phases/__init__.py`, `requirements.txt`; copy `no_console.py errors.py utils.py progress.py heartbeat.py stage_summary.py sdk_client.py`.

- [ ] **Step 1: `requirements.txt`** — `langgraph>=0.2`, `langgraph-checkpoint-sqlite>=2.0`, `claude-agent-sdk>=0.1`, `tenacity>=8`, `pytest>=8`, `jsonschema>=4`.
- [ ] **Step 2: Empty `albert/__init__.py`, `albert/phases/__init__.py`.**
- [ ] **Step 3: Copy + rename infra:**

```bash
for f in no_console.py errors.py utils.py progress.py heartbeat.py stage_summary.py sdk_client.py; do
  sed -e 's/ai_escape_mrc/albert/g' -e 's/AI Escape MRC/Albert/g' \
    "D:/D-claude/skills/skill-ai-escape-mrc/ai_escape_mrc/$f" > "albert/$f"
done
```

- [ ] **Step 4: Add `DegradedEmissionError` to `albert/errors.py`** (keep `VisibilityContractError`; drop Phase9*/OutputIdentity):

```python
class DegradedEmissionError(Exception):
    """A degraded run (status=='failed') tried to emit a non-refusal verdict/green light."""
    def __init__(self, message: str, predicate: str = "") -> None:
        super().__init__(message)
        self.predicate = predicate
```

- [ ] **Step 5: Verify:** `py -3 -c "import albert.sdk_client, albert.progress, albert.heartbeat, albert.utils, albert.errors, albert.stage_summary, albert.no_console"` → exit 0.
- [ ] **Step 6: Commit** `feat: scaffold albert package + copy proven infra`.

---

## Task 2: `albert/models.py`

**Files:** Create `albert/models.py`; Test `tests/test_models_routing.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_models_routing.py
from albert.models import model_for_role, model_label

def test_strong_roles_default():
    for r in ("challenge_generation", "self_critique_audit", "signals_action_gate", "verdict_render"):
        assert model_for_role(r) is None

def test_fast_env_routes_non_strong(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODEL", "claude-sonnet-4-6")
    assert model_for_role("ambiguity_hunt") == "claude-sonnet-4-6"
    assert model_for_role("self_critique_audit") is None

def test_label():
    assert model_label(None) == "environment-default"
```

- [ ] **Step 2: Run → FAIL.** `py -3 -m pytest tests/test_models_routing.py -v`
- [ ] **Step 3: Implement**

```python
"""Model routing. Reasoning-heavy roles stay on the strong session default."""
from __future__ import annotations
import os

ENVIRONMENT_DEFAULT_MODEL_LABEL = "environment-default"
_STRONG_ROLES = frozenset({"challenge_generation", "self_critique_audit",
                           "signals_action_gate", "verdict_render"})
_FAST_MODEL_ENV = "ALBERT_FAST_MODEL"


def model_for_role(role: str) -> str | None:
    if role in _STRONG_ROLES:
        return None
    return (os.environ.get(_FAST_MODEL_ENV) or "").strip() or None


def model_label(model: str | None) -> str:
    return model or ENVIRONMENT_DEFAULT_MODEL_LABEL
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat: model routing`.

---

## Task 3: `albert/state.py`

**Files:** Create `albert/state.py`; Test `tests/test_state_shape.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_state_shape.py
from albert.state import (AlbertState, GENERATORS, CHALLENGE_STATUSES,
                          DECISIONS, AUDIT_VERDICTS, RISK_LEVELS)

def test_generators_six():
    assert len(GENERATORS) == 6 and "convergence_redteam" in GENERATORS

def test_statuses_eight():
    assert len(CHALLENGE_STATUSES) == 8 and "needs_albert_decision" in CHALLENGE_STATUSES

def test_decisions_eight():
    assert DECISIONS == ["continue_research", "branch", "rerank", "pull_human",
                         "push_human", "synthesize", "pause", "terminal_stop"]

def test_audit_verdicts():
    assert AUDIT_VERDICTS == ["continue", "exhausted", "rework"]

def test_risk_levels():
    assert RISK_LEVELS == ["low", "medium", "high"]

def test_total_false():
    s: AlbertState = {}
    s["current_answer"] = "x"
    assert s["current_answer"] == "x"
```

- [ ] **Step 2: Run → FAIL.** `py -3 -m pytest tests/test_state_shape.py -v`
- [ ] **Step 3: Implement**

```python
"""AlbertState: LangGraph state for the Albert Thought Agent FSM."""
import operator
from typing import Annotated, TypedDict, Literal, Optional


def _take_last(_a, b):
    return b


GENERATORS = ["winning", "first_principle", "timing",
              "competitor", "owner_business", "convergence_redteam"]
CHALLENGE_STATUSES = [
    "answered", "partially_answered", "needs_external_research", "needs_internal_data",
    "needs_bu_judgment", "needs_albert_decision", "needs_source_validation", "blocked"]
DECISIONS = ["continue_research", "branch", "rerank", "pull_human",
             "push_human", "synthesize", "pause", "terminal_stop"]
AUDIT_VERDICTS = ["continue", "exhausted", "rework"]
RISK_LEVELS = ["low", "medium", "high"]


class AlbertState(TypedDict, total=False):
    # Input (the albert_input contract, normalized)
    albert_input: dict
    mode: Literal["cockpit", "standalone"]
    current_answer: str
    original_objective: str
    meeting_context: str
    output_purpose: str
    issue_map: list[dict]
    challenge_map: list[dict]
    evidence: list[dict]
    skeptic_output: list[str]
    source_critic_output: list[str]
    readiness_scores: dict
    recent_research_actions: list[str]
    research_state: dict
    proposal: dict
    run_id: str
    run_dir: str
    user_email: Optional[str]

    # Visibility accumulators
    screen_summary: Annotated[Optional[str], _take_last]
    stage_summaries: Annotated[list[dict], operator.add]
    stage_summaries_path: Annotated[Optional[str], _take_last]
    visibility_receipt: Annotated[dict, _take_last]

    # Phase 0
    phase_0_complete: bool
    phase_0_status: Optional[Literal["passed", "failed"]]
    research: list[dict]
    meta_question: dict

    # Phase 1
    phase_1_complete: bool
    phase_1_status: Optional[Literal["passed", "failed"]]
    top_ambiguities: list[dict]

    # Phase 2
    phase_2_complete: bool
    phase_2_status: Optional[Literal["passed", "failed"]]
    albert_challenges: list[dict]
    weak_points: list[str]
    missing_business_context: list[str]
    would_survive_leadership: Optional[bool]

    # Phase 3 (exhaustion loop with phase 2)
    phase_3_complete: bool
    phase_3_status: Optional[Literal["passed", "failed"]]
    phase_3_rounds: list[dict]
    phase_3_verdict: Optional[Literal["EXHAUSTED", "REWORK"]]
    phase_3_attempt_count: int

    # Phase 4
    phase_4_complete: bool
    phase_4_status: Optional[Literal["passed", "failed"]]
    missing_evidence: list[dict]
    questions_albert_would_ask: list[str]
    premature_end_risk: dict
    research_drift_risk: dict
    recommended_next_probe: list[dict]
    recommended_next_action: Optional[str]
    rationale: str
    decision_gate: dict
    reproducible_judgment: str

    # Phase 5
    phase_5_complete: bool
    verdict: Optional[str]                 # AuditVerdict: continue|exhausted|rework
    degraded: bool
    run_status: Optional[Literal["passed", "failed"]]
    readiness_score_delta: int
    verdict_standalone: Optional[str]      # 可推進|要補證據|方向錯|產品定義不完整
    light: Optional[Literal["green", "yellow", "red"]]
    report_path: Optional[str]
    challenge_json_path: Optional[str]
    email_delivery_result: Optional[str]
    email_delivery_error: Optional[str]

    start_time: str
    end_time: Optional[str]
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat: AlbertState v0.4 (AuditResult-aligned + frozen enums)`.

---

## Task 4: `albert/schemas.py` + disk contract files

**Files:** Create `albert/schemas.py`, `schemas/albert_input.schema.json`, `schemas/albert_challenge.schema.json`; Test `tests/test_albert_challenge_schema.py`, `tests/test_albert_input_schema.py`.

- [ ] **Step 1: Failing tests**

```python
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
```

```python
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
```

- [ ] **Step 2: Run → FAIL.** `py -3 -m pytest tests/test_albert_challenge_schema.py tests/test_albert_input_schema.py -v`
- [ ] **Step 3: Implement `albert/schemas.py`**

```python
"""StructuredOutput JSON schemas, aligned to the cockpit's AuditResult. Top-level type 'object'."""

GENERATOR_ENUM = ["winning", "first_principle", "timing",
                  "competitor", "owner_business", "convergence_redteam"]
STATUS_ENUM = ["answered", "partially_answered", "needs_external_research", "needs_internal_data",
               "needs_bu_judgment", "needs_albert_decision", "needs_source_validation", "blocked"]
DECISION_ENUM = ["continue_research", "branch", "rerank", "pull_human",
                 "push_human", "synthesize", "pause", "terminal_stop"]
VERDICT_ENUM = ["continue", "exhausted", "rework"]
LEVEL_ENUM = ["low", "medium", "high"]
STRENGTH_ENUM = ["weak", "medium", "strong"]

SEARCH_REFLECTION = {
    "type": "object",
    "properties": {
        "reframing": {"type": "string"},
        "higher_level_question": {"type": "string"},
        "wave2_queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
    },
    "required": ["higher_level_question", "wave2_queries"],
}

AMBIGUITY_HUNT = {
    "type": "object",
    "properties": {"top_ambiguities": {"type": "array", "items": {"type": "object", "properties": {
        "term": {"type": "string"}, "why_dangerous": {"type": "string"},
        "precise_question": {"type": "string"}},
        "required": ["term", "why_dangerous", "precise_question"]}, "minItems": 3, "maxItems": 3}},
    "required": ["top_ambiguities"],
}

_CHALLENGE_ITEM = {
    "type": "object",
    "properties": {
        "challenge": {"type": "string"},
        "why_albert_would_ask": {"type": "string"},
        "current_answer": {"type": "string"},
        "status": {"type": "string", "enum": STATUS_ENUM},
        "confidence": {"type": "string", "enum": LEVEL_ENUM},
        "severity": {"type": "string", "enum": LEVEL_ENUM},
        "current_answer_strength": {"type": "string", "enum": STRENGTH_ENUM},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "missing_info": {"type": "string"},
        "blocking_owner": {"type": "string"},
        "next_action": {"type": "string"},
        "meeting_ready_response": {"type": "string"},
        "recommended_probe": {"type": "string"},
        "generator": {"type": "string", "enum": GENERATOR_ENUM},
        "bone": {"type": "integer", "minimum": 1, "maximum": 12},
        "high_impact": {"type": "boolean"},
    },
    "required": ["challenge", "why_albert_would_ask", "status", "severity",
                 "current_answer_strength", "generator", "bone"],
}

CHALLENGE_GENERATION = {
    "type": "object",
    "properties": {
        "albert_challenges": {"type": "array", "items": _CHALLENGE_ITEM, "minItems": 1},
        "weak_points": {"type": "array", "items": {"type": "string"}},
        "missing_business_context": {"type": "array", "items": {"type": "string"}},
        "would_survive_leadership": {"type": "boolean"},
    },
    "required": ["albert_challenges", "weak_points", "would_survive_leadership"],
}

SELF_CRITIQUE_AUDIT = {
    "type": "object",
    "properties": {
        "round": {"type": "integer"},
        "weaknesses": {"type": "array", "items": {"type": "object", "properties": {
            "challenge_index": {"type": ["integer", "null"]},
            "classification": {"type": "string", "enum": ["addressable", "residual"]},
            "issue": {"type": "string"}, "suggested_sharpening": {"type": "string"}},
            "required": ["classification", "issue"]}},
        "verdict": {"type": "string", "enum": ["continue", "exhausted", "rework"]},
    },
    "required": ["round", "weaknesses", "verdict"],
}

# Phase 4 LLM produces atoms + a PROPOSED action + rationale; signals.py computes
# the risk levels and vetoes an action inconsistent with the signals.
SIGNALS_ACTION_GATE = {
    "type": "object",
    "properties": {
        "missing_evidence": {"type": "array", "items": {"type": "object", "properties": {
            "item": {"type": "string"},
            "who_can_answer": {"type": "string", "enum": ["AI", "public", "internal", "customer"]}},
            "required": ["item", "who_can_answer"]}},
        "questions_albert_would_ask": {"type": "array", "items": {"type": "string"}},
        "premature_end_atoms": {"type": "object", "properties": {
            "open_high_impact_challenges": {"type": "integer", "minimum": 0},
            "new_info_rate": {"type": "string", "enum": ["high", "medium", "low", "none", "unknown"]},
            "challenge_map_mostly_classified": {"type": "boolean"},
            "unresolved_are_human_data_decision_only": {"type": "boolean"},
            "meta_question_search_found_new_high_impact_angle": {"type": "boolean"}},
            "required": ["open_high_impact_challenges", "new_info_rate"]},
        "drift_atoms": {"type": "object", "properties": {
            "current_focus_in_original_high_value_set": {"type": "boolean"},
            "high_value_branch_ignored": {"type": "boolean"}}},
        "recommended_next_probe": {"type": "array", "items": {"type": "object", "properties": {
            "probe": {"type": "string"}, "why": {"type": "string"},
            "kind": {"type": "string", "enum": ["meta", "object"]},
            "impact": {"type": "string", "enum": LEVEL_ENUM},
            "answerability": {"type": "string", "enum": LEVEL_ENUM}},
            "required": ["probe", "why"]}},
        "proposed_next_action": {"type": "string", "enum": DECISION_ENUM},
        "rationale": {"type": "string"},
        "decision_gate": {"type": "object", "properties": {
            "can_decide_now": {"type": "array", "items": {"type": "string"}},
            "cannot_decide": {"type": "array", "items": {"type": "string"}},
            "owners": {"type": "array", "items": {"type": "object", "properties": {
                "area": {"type": "string"}, "owner": {"type": "string"}},
                "required": ["area", "owner"]}}},
            "required": ["can_decide_now", "cannot_decide", "owners"]},
        "reproducible_judgment": {"type": "string"},
    },
    "required": ["premature_end_atoms", "proposed_next_action", "decision_gate"],
}

VERDICT = {
    "type": "object",
    "properties": {
        "verdict_standalone": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
        "readiness_score_delta": {"type": "integer", "minimum": -2, "maximum": 2},
    },
    "required": ["verdict_standalone", "light", "readiness_score_delta"],
}

_RISK = {"type": "object", "properties": {
    "level": {"type": "string", "enum": LEVEL_ENUM}, "atoms": {"type": "object"},
    "grounded_in": {"type": "string", "enum": ["research_state", "inferred"]},
    "why": {"type": "string"}, "low_confidence": {"type": "boolean"}}, "required": ["level", "grounded_in"]}

ALBERT_CHALLENGE = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": VERDICT_ENUM},
        "audited_answer": {"type": "string"},
        "would_survive_leadership": {"type": "boolean"},
        "top_ambiguities": AMBIGUITY_HUNT["properties"]["top_ambiguities"],
        "albert_challenges": {"type": "array", "items": _CHALLENGE_ITEM},
        "weak_points": {"type": "array", "items": {"type": "string"}},
        "missing_business_context": {"type": "array", "items": {"type": "string"}},
        "missing_evidence": SIGNALS_ACTION_GATE["properties"]["missing_evidence"],
        "questions_albert_would_ask": {"type": "array", "items": {"type": "string"}},
        "premature_end_risk": _RISK,
        "research_drift_risk": _RISK,
        "recommended_next_probe": SIGNALS_ACTION_GATE["properties"]["recommended_next_probe"],
        "recommended_next_action": {"type": "string", "enum": DECISION_ENUM},
        "rationale": {"type": "string"},
        "decision_gate": SIGNALS_ACTION_GATE["properties"]["decision_gate"],
        "readiness_score_delta": {"type": "integer", "minimum": -2, "maximum": 2},
        "reproducible_judgment": {"type": "string"},
        "degraded": {"type": "boolean"},
        "run_status": {"type": "string", "enum": ["passed", "failed"]},
        "verdict_standalone": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
    },
    "required": ["verdict", "albert_challenges", "weak_points", "premature_end_risk",
                 "research_drift_risk", "recommended_next_action", "rationale", "degraded"],
}

ALBERT_INPUT = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["cockpit", "standalone"]},
        "current_answer": {"type": "string"},
        "original_objective": {"type": "string"},
        "meeting_context": {"type": "string"},
        "output_purpose": {"type": "string",
            "enum": ["meeting_defense", "decision_readiness", "find_blockers", "exec_memo"]},
        "issue_map": {"type": "array", "items": {"type": "object"}},
        "challenge_map": {"type": "array", "items": {"type": "object"}},
        "evidence": {"type": "array", "items": {"type": "object"}},
        "skeptic_output": {"type": "array", "items": {"type": "string"}},
        "source_critic_output": {"type": "array", "items": {"type": "string"}},
        "readiness_scores": {"type": "object"},
        "recent_research_actions": {"type": "array", "items": {"type": "string"}},
        "research_state": {"type": "object"},
        "proposal": {"type": "object", "properties": {
            "title": {"type": "string"}, "body": {"type": "string"}, "domain": {"type": "string"}}},
    },
    "required": ["current_answer", "mode"],
}
```

- [ ] **Step 4: Generate disk schema files**

```bash
py -3 -c "import json; from albert import schemas; \
open('schemas/albert_challenge.schema.json','w',encoding='utf-8').write(json.dumps({'\$schema':'https://json-schema.org/draft/2020-12/schema','title':'AlbertChallenge', **schemas.ALBERT_CHALLENGE}, ensure_ascii=False, indent=2)); \
open('schemas/albert_input.schema.json','w',encoding='utf-8').write(json.dumps({'\$schema':'https://json-schema.org/draft/2020-12/schema','title':'AlbertInput', **schemas.ALBERT_INPUT}, ensure_ascii=False, indent=2))"
```

- [ ] **Step 5: Run → PASS. Step 6: Commit** `feat: v0.4 schemas aligned to cockpit AuditResult`.

---

## Task 5: `albert/signals.py` — rule engine + action-consistency

**Files:** Create `albert/signals.py`; Test `tests/test_signals_grounding.py`, `tests/test_action_consistency.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_signals_grounding.py
from albert.signals import premature_end_level, drift_level, rank_next_probe, grounding_of

_STOP_OK = {"open_high_impact_challenges": 0, "new_info_rate": "low",
            "challenge_map_mostly_classified": True, "unresolved_are_human_data_decision_only": True,
            "meta_question_search_found_new_high_impact_angle": False}

def test_all_stop_met_low(): assert premature_end_level(_STOP_OK) == "low"
def test_two_violations_high():
    assert premature_end_level(dict(_STOP_OK, open_high_impact_challenges=2, new_info_rate="high")) == "high"
def test_meta_question_blocks_low():
    assert premature_end_level(dict(_STOP_OK, meta_question_search_found_new_high_impact_angle=True)) != "low"
def test_drift_low():
    assert drift_level({"current_focus_in_original_high_value_set": True, "high_value_branch_ignored": False}) == "low"
def test_drift_high():
    assert drift_level({"current_focus_in_original_high_value_set": False, "high_value_branch_ignored": True}) == "high"
def test_grounding():
    assert grounding_of({}) == "inferred"
    assert grounding_of({"branches_explored": ["a"]}) == "research_state"
def test_rank():
    r = rank_next_probe([{"probe": "a", "impact": "low", "answerability": "high"},
                         {"probe": "b", "impact": "high", "answerability": "low"}])
    assert r[0]["probe"] == "b" and r[0]["priority"] == 1
```

```python
# tests/test_action_consistency.py
from albert.signals import enforce_action_consistency

def test_high_premature_blocks_synthesize():
    a = enforce_action_consistency("synthesize", premature="high", drift="low", evidence=[])
    assert a not in ("synthesize", "terminal_stop")
    assert a == "continue_research"

def test_high_premature_blocks_terminal():
    assert enforce_action_consistency("terminal_stop", premature="high", drift="low", evidence=[]) == "continue_research"

def test_high_drift_forces_rerank_or_pull():
    assert enforce_action_consistency("continue_research", premature="low", drift="high", evidence=[]) in ("rerank", "pull_human")

def test_customer_residual_forces_push_or_pull():
    ev = [{"item": "x", "who_can_answer": "customer"}, {"item": "y", "who_can_answer": "customer"}]
    assert enforce_action_consistency("synthesize", premature="low", drift="low", evidence=ev) in ("push_human", "pull_human")

def test_consistent_action_passes_through():
    assert enforce_action_consistency("branch", premature="low", drift="low", evidence=[]) == "branch"
```

- [ ] **Step 2: Run → FAIL.** `py -3 -m pytest tests/test_signals_grounding.py tests/test_action_consistency.py -v`
- [ ] **Step 3: Implement `albert/signals.py`**

```python
"""Deterministic rule engine for the loop signals + action-consistency guard.

Risk levels are pure functions of named atoms (spec §4 / consumer §9.3) — never an
LLM gestalt. The recommended next action is LLM-proposed but vetoed here when it
contradicts the signals."""
from __future__ import annotations

_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0, "unknown": 1}


def grounding_of(research_state: dict | None) -> str:
    if research_state and any(research_state.get(k) for k in
                              ("branches_explored", "branches_open", "rounds_so_far",
                               "new_info_rate", "stage_summary")):
        return "research_state"
    return "inferred"


def premature_end_level(atoms: dict) -> str:
    """High = §9.3 'safe to stop' conditions NOT all met. 0 violations->low, 1->medium, >=2->high."""
    violations = 0
    if atoms.get("new_info_rate") not in ("low", "none"):
        violations += 1
    if atoms.get("meta_question_search_found_new_high_impact_angle"):
        violations += 1
    if int(atoms.get("open_high_impact_challenges", 0) or 0) > 0:
        violations += 1
    if not atoms.get("challenge_map_mostly_classified", False):
        violations += 1
    if not atoms.get("unresolved_are_human_data_decision_only", False):
        violations += 1
    if violations == 0:
        return "low"
    return "high" if violations >= 2 else "medium"


def drift_level(atoms: dict) -> str:
    in_set = atoms.get("current_focus_in_original_high_value_set", True)
    ignored = atoms.get("high_value_branch_ignored", False)
    if in_set and not ignored:
        return "low"
    if (not in_set) and ignored:
        return "high"
    return "medium"


def rank_next_probe(probes: list[dict]) -> list[dict]:
    def key(p):
        return (_RANK.get(p.get("impact", "medium"), 2), _RANK.get(p.get("answerability", "medium"), 2))
    ranked = sorted(list(probes or []), key=key, reverse=True)
    for i, p in enumerate(ranked, 1):
        p["priority"] = i
    return ranked


def build_risk(level: str, atoms: dict, research_state: dict | None, why: str = "") -> dict:
    grounded = grounding_of(research_state)
    return {"level": level, "atoms": atoms, "grounded_in": grounded,
            "why": why, "low_confidence": grounded == "inferred"}


def enforce_action_consistency(proposed: str, premature: str, drift: str, evidence: list[dict]) -> str:
    """Veto an LLM-proposed next action that contradicts the rule-grounded signals.
    Albert RECOMMENDS; the cockpit still decides. Order: premature > drift > evidence."""
    if premature == "high" and proposed in ("synthesize", "terminal_stop"):
        return "continue_research"           # not done — keep researching
    if drift == "high" and proposed not in ("rerank", "pull_human"):
        return "rerank"                       # off-track — re-rank toward the objective
    customer_only = [e for e in (evidence or []) if e.get("who_can_answer") == "customer"]
    if len(customer_only) >= 2 and proposed in ("synthesize", "terminal_stop", "continue_research"):
        return "push_human"                   # the blocker is the customer, not more AI research
    return proposed
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat: rule engine + action-consistency guard`.

---

## Task 6: Prompts

**Files:** Create the 8 prompt files; Test `tests/test_prompts_present.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_prompts_present.py
import pytest
from albert.utils import load_prompt
NAMES = ["albert_persona","intake_grounding","search_reflection","ambiguity_hunt",
         "challenge_generation","self_critique_auditor","signals_action_gate","verdict_render"]

@pytest.mark.parametrize("n", NAMES)
def test_loads(n): assert len(load_prompt(n)) > 50

def test_persona_twelve_bones():
    t = load_prompt("albert_persona")
    for n in range(1, 13): assert f"{n}." in t

def test_persona_durability():
    assert "durab" in load_prompt("albert_persona").lower() or "moat" in load_prompt("albert_persona").lower()

def test_auditor_adversarial():
    assert "adversarial" in load_prompt("self_critique_auditor").lower()

def test_signals_prompt_demands_atoms_and_action():
    t = load_prompt("signals_action_gate").lower()
    assert "atom" in t and "proposed_next_action" in t and "do not output the final" in t
```

- [ ] **Step 2: Run → FAIL.** `py -3 -m pytest tests/test_prompts_present.py -v`
- [ ] **Step 3: Write `albert/prompts/albert_persona.txt`** (12 bones; verbatim from spec §2, plus the soul-grade durability clause):

```
You are Albert — a high-standard product & architecture war-room reviewer, a BU-head
mind. You do NOT praise and do NOT summarize. You force DECISION QUALITY.

The 12 bones:
1. Force every vague term into a precise definition.
2. Ask "will it win?" of every feature (must-have / nice-to-have / overkill / parity).
3. Decompose to first principles (application -> service -> latency/deterministic/safety/availability -> compute placement).
4. Chase local-vs-central compute (command-down vs signal-up; actuator / BLDC controller).
5. Use latency / deterministic numbers to bring fantasy back to reality.
6. Reverse-engineer competitor strategy (segment; tech/cost/customer/legacy; last-gen benchmark; next-gen roadmap).
7. Force a single owner (no 多頭馬車; who decides; pre-feasibility; binding risk + fallback).
8. Separate internal central thesis from external framing.
9. Converge the war-room NOW (answerable now vs needs customer; 30-point version).
10. Ask spec + business + schedule together.
11. Red-team the central thesis (where wrong; who is the contrarian).
12. Chase reproducible judgment, not one-off answers.

A question is "soul-grade" only if it (a) targets decision quality not document
completeness, (b) forces a thesis, (c) is research-backed, and (d) probes DURABILITY:
not just "will it win" but "is the advantage durable or will it be copied/commoditized"
(the moat test). Output language: match the input.
```

- [ ] **Step 4: Write the other 7 prompts** with these exact contents:

`intake_grounding.txt`:
```
You are Albert preparing to audit a CURRENT ANSWER. Read the current answer, its domain,
the meeting_context, and the output_purpose. Decide what external facts you need to ground
a sharp audit: competitor segment cuts, competitor next-gen roadmap, what a mature SOTA
product would do, public latency/cost benchmarks. Output 1-5 wave-1 search queries specific
to THIS answer's domain. Do NOT research the issue branches themselves (that is the cockpit's
job) — only meta-research that grounds the challenge.
```

`search_reflection.txt`:
```
You are Albert reflecting between research waves. Given the current answer and wave-1 results,
find the HIGHER-LEVEL meta-question the answer is NOT addressing ("what would a mature SOTA
product do?"; "is this benchmarking last gen?"). Output reframing, higher_level_question, and
1-4 wave-2 queries to confirm whether a new high-impact angle exists. Emit StructuredOutput.
```

`ambiguity_hunt.txt`:
```
You are Albert (bone 1). Read the current answer. List the vague terms that hide a decision,
then select the THREE most DANGEROUS — those whose ambiguity would most likely sink the
decision in a leadership meeting. For each: term, why dangerous, the precise question that
forces a definition. Emit StructuredOutput only.
```

`challenge_generation.txt`:
```
You are Albert (bones 2-11) auditing a CURRENT ANSWER. You are given the dangerous ambiguities,
research facts, the meta-question, and the Skeptic's and Source Critic's prior output — BUILD
ON those, do not redo them. Tune emphasis to output_purpose (meeting_defense -> red-team +
would-survive; find_blockers -> owner/convergence). Produce albert_challenges: each with
challenge, why_albert_would_ask, current_answer (what the answer says about it), a status from
{answered, partially_answered, needs_external_research, needs_internal_data, needs_bu_judgment,
needs_albert_decision, needs_source_validation, blocked}, confidence, SEVERITY (how damaging),
CURRENT_ANSWER_STRENGTH (weak/medium/strong), missing_info, blocking_owner, next_action,
meeting_ready_response, recommended_probe, generator, bone, high_impact. Also weak_points (each
a single sentence string), missing_business_context, would_survive_leadership. Each challenge
must be soul-grade and research-backed. Do NOT pad to a fixed count. Emit StructuredOutput.
```

`self_critique_auditor.txt`:
```
You are an ADVERSARIAL auditor of Albert's own challenges. You do NOT agree easily. For each
challenge: sharp, or WEAK? Classify each weakness addressable (too vague/generic — give the
sharpening) or residual (only the customer can resolve). Verdict rework if any addressable
weakness remains; exhausted if every remaining weakness is residual; continue if more research
is warranted before judging. Never rubber-stamp; but do NOT invent flaws in a sound challenge
just to look busy. Emit StructuredOutput.
```

`signals_action_gate.txt`:
```
You are Albert producing the loop-signal ATOMS, a PROPOSED next action, and the decision gate.
Given the current answer, challenges, research_state telemetry, readiness_scores, and the
meta-question result, output:
- premature_end_atoms: open_high_impact_challenges (count), new_info_rate, challenge_map_mostly_classified,
  unresolved_are_human_data_decision_only, meta_question_search_found_new_high_impact_angle.
- drift_atoms: current_focus_in_original_high_value_set, high_value_branch_ignored.
- recommended_next_probe (kind meta/object, impact, answerability), missing_evidence (who_can_answer),
  questions_albert_would_ask, decision_gate (can_decide_now/cannot_decide/owners), reproducible_judgment.
- proposed_next_action: one of continue_research|branch|rerank|pull_human|push_human|synthesize|pause|
  terminal_stop, and a rationale.
IMPORTANT: report the ATOMS and a PROPOSED action only. Do NOT output the final risk LEVELS —
the system computes the levels from your atoms and may veto an inconsistent action. Emit StructuredOutput.
```

`verdict_render.txt`:
```
You are Albert delivering the standalone one-line judgment. Given the ambiguities, challenges,
risks, and decision gate, choose exactly one verdict_standalone (可推進 / 要補證據 / 方向錯 /
產品定義不完整), a light (green/yellow/red), and readiness_score_delta in [-2, 2]. An answer with
unresolved dangerous ambiguities, high premature_end_risk, or customer-only residual evidence
cannot be green. Emit StructuredOutput.
```

- [ ] **Step 5: Run → PASS. Step 6: Commit** `feat: 12-bone persona + 7 phase prompts (v0.4)`.

---

## Task 7: `albert/input_adapter.py` + Phase 0

**Files:** Create `albert/input_adapter.py`, `albert/phases/phase_0_intake_grounding.py`; Test `tests/test_input_adapter.py`, `tests/test_phase_0_intake.py`.

- [ ] **Step 1: Failing tests**

```python
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
```

```python
# tests/test_phase_0_intake.py
from albert.phases.phase_0_intake_grounding import phase_0_intake_grounding

def test_phase_0_grounds_and_reflects(monkeypatch):
    import albert.phases.phase_0_intake_grounding as m
    monkeypatch.setattr(m, "call_claude", lambda **k:
        {"queries": ["q1"]} if k["purpose"] == "intake_grounding"
        else {"reframing": "r", "higher_level_question": "hq", "wave2_queries": ["q2"]})
    monkeypatch.setattr(m, "websearch", lambda q: {"query": q, "results": "SOTA moved compute to zone"})
    state = {"albert_input": {"current_answer": "zonal controller, no spec", "mode": "standalone",
             "proposal": {"domain": "auto"}, "research_state": {}, "meeting_context": "BU review"}}
    out = phase_0_intake_grounding(state)
    assert out["phase_0_complete"] and out["current_answer"]
    assert out["meta_question"]["higher_level_question"] == "hq"
    assert isinstance(out["research"], list) and out["research"]
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `albert/input_adapter.py`**

```python
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
```

- [ ] **Step 4: Implement `albert/phases/phase_0_intake_grounding.py`** (same as v0.3 but also copies the enriched fields into state):

```python
"""Phase 0: parse §20 input + META-research grounding (wave-1 -> reflect -> wave-2).
Meta-research only; object-research is the cockpit's job. websearch() never raises."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude, websearch
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas

_QUERIES_SCHEMA = {"type": "object", "properties": {
    "queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5}},
    "required": ["queries"]}

_CARRY = ["current_answer", "original_objective", "meeting_context", "output_purpose",
          "issue_map", "challenge_map", "evidence", "skeptic_output", "source_critic_output",
          "readiness_scores", "recent_research_actions", "research_state", "proposal"]


def phase_0_intake_grounding(state: dict) -> dict:
    inp = state["albert_input"]
    state["mode"] = inp.get("mode", "standalone")
    for k in _CARRY:
        state[k] = inp.get(k, "" if k in ("current_answer", "original_objective", "meeting_context", "output_purpose") else ({} if k in ("research_state", "readiness_scores", "proposal") else []))

    ctx = (f"Current answer:\n{state['current_answer'][:6000]}\n\n"
           f"Domain: {state['proposal'].get('domain','')}\nMeeting: {state.get('meeting_context','')}\n"
           f"Output purpose: {state.get('output_purpose','')}\n")
    status, research, meta = "passed", [], {}
    try:
        plan = call_claude(model=model_for_role("intake_grounding"),
                           system=load_prompt("intake_grounding"), user=ctx,
                           json_schema=_QUERIES_SCHEMA, purpose="intake_grounding")
        wave1 = [websearch(q) for q in (plan.get("queries") or [])[:5]]
        research.extend(wave1)
        refl_ctx = ctx + "\nWave-1 results:\n" + "\n".join(
            f"- {r['query']}: {str(r.get('results',''))[:300]}" for r in wave1)
        meta = call_claude(model=model_for_role("intake_grounding"),
                           system=load_prompt("search_reflection"), user=refl_ctx,
                           json_schema=schemas.SEARCH_REFLECTION, purpose="search_reflection")
        research.extend(websearch(q) for q in (meta.get("wave2_queries") or [])[:4])
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_0 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        status = "failed"
    state["research"], state["meta_question"] = research, meta or {}
    state["phase_0_status"], state["phase_0_complete"] = status, True
    return state
```

- [ ] **Step 5: Run → PASS. Step 6: Commit** `feat: phase 0 intake + meta-research; enriched dual-mode adapter`.

---

## Task 8: Phase 1 — ambiguity hunt

(unchanged from v0.3 — `current_answer` based)

**Files:** Create `albert/phases/phase_1_ambiguity_hunt.py`; Test `tests/test_phase_1_ambiguity.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_phase_1_ambiguity.py
from albert.phases.phase_1_ambiguity_hunt import phase_1_ambiguity_hunt
def _a(t): return {"term": t, "why_dangerous": "w", "precise_question": "p"}
def test_three(monkeypatch):
    import albert.phases.phase_1_ambiguity_hunt as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"top_ambiguities": [_a("a"), _a("b"), _a("c")]})
    out = phase_1_ambiguity_hunt({"current_answer": "no spec", "research": []})
    assert len(out["top_ambiguities"]) == 3 and out["phase_1_status"] == "passed"
def test_stub(monkeypatch):
    import albert.phases.phase_1_ambiguity_hunt as m
    monkeypatch.setattr(m, "call_claude", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = phase_1_ambiguity_hunt({"current_answer": "x", "research": []})
    assert len(out["top_ambiguities"]) == 3 and out["phase_1_status"] == "failed"
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
"""Phase 1 (bone 1): top-3 dangerous ambiguities in the current answer."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas


def _stub():
    return [{"term": "(LLM unavailable)", "why_dangerous": "review could not run",
             "precise_question": "re-run Albert when transport is available"} for _ in range(3)]


def phase_1_ambiguity_hunt(state: dict) -> dict:
    digest = "\n".join(f"- {r.get('query','')}: {str(r.get('results',''))[:300]}"
                       for r in (state.get("research") or [])[:3])
    ctx = f"Current answer:\n{state.get('current_answer','')[:6000]}\n\nResearch:\n{digest}\n"
    status = "passed"
    try:
        res = call_claude(model=model_for_role("ambiguity_hunt"), system=load_prompt("ambiguity_hunt"),
                          user=ctx, json_schema=schemas.AMBIGUITY_HUNT, purpose="ambiguity_hunt")
        top = res.get("top_ambiguities") or []
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_1 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        top, status = _stub(), "failed"
    if not isinstance(top, list) or len(top) < 3:
        top = (top or []) + _stub()
    state["top_ambiguities"], state["phase_1_status"], state["phase_1_complete"] = top[:3], status, True
    return state
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat: phase 1 ambiguity hunt`.

---

## Task 9: Phase 2 — challenge generation (§17+§20 superset)

**Files:** Create `albert/phases/phase_2_challenge_generation.py`; Test `tests/test_phase_2_challenge.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_phase_2_challenge.py
from albert.phases.phase_2_challenge_generation import phase_2_challenge_generation

def _resp():
    return {"albert_challenges": [{"challenge": "why win?", "why_albert_would_ask": "parity",
            "status": "needs_bu_judgment", "severity": "high", "current_answer_strength": "weak",
            "generator": "winning", "bone": 2, "high_impact": True}],
        "weak_points": ["no ROI number"], "missing_business_context": ["TAM"], "would_survive_leadership": False}

def test_generates(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp())
    out = phase_2_challenge_generation({"current_answer": "x", "research": [], "top_ambiguities": [],
        "meta_question": {}, "skeptic_output": [], "source_critic_output": [], "output_purpose": "meeting_defense"})
    assert out["albert_challenges"][0]["severity"] == "high"
    assert out["weak_points"] == ["no ROI number"]
    assert out["would_survive_leadership"] is False and out["phase_2_status"] == "passed"

def test_rework_feedback(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    cap = {}
    monkeypatch.setattr(m, "call_claude", lambda **k: (cap.__setitem__("u", k["user"]), _resp())[1])
    phase_2_challenge_generation({"current_answer": "x", "research": [], "top_ambiguities": [],
        "meta_question": {}, "skeptic_output": [], "source_critic_output": [], "output_purpose": "x",
        "phase_3_rounds": [{"weaknesses": [{"classification": "addressable", "issue": "v", "suggested_sharpening": "tie to roadmap"}]}]})
    assert "tie to roadmap" in cap["u"]

def test_stub(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = phase_2_challenge_generation({"current_answer": "x", "research": [], "top_ambiguities": [],
        "meta_question": {}, "skeptic_output": [], "source_critic_output": [], "output_purpose": "x"})
    assert out["phase_2_status"] == "failed" and out["albert_challenges"]
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
"""Phase 2 (bones 2-11): generate albert_challenges against the current answer, building on
the Skeptic + Source Critic output. Rework loop feeds prior addressable sharpenings back."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas


def _stub():
    return {"albert_challenges": [{"challenge": "(LLM unavailable — re-run Albert)",
            "why_albert_would_ask": "n/a", "status": "blocked", "severity": "high",
            "current_answer_strength": "weak", "generator": "winning", "bone": 2}],
            "weak_points": [], "missing_business_context": [], "would_survive_leadership": False}


def _prior_sharpenings(state):
    rounds = state.get("phase_3_rounds") or []
    if not rounds:
        return ""
    fixes = [w.get("suggested_sharpening", "") for w in rounds[-1].get("weaknesses", [])
             if isinstance(w, dict) and w.get("classification") == "addressable" and w.get("suggested_sharpening")]
    return ("Prior audit said these were too weak — sharpen them:\n" + "\n".join(f"- {f}" for f in fixes) + "\n\n") if fixes else ""


def _lines(items, n=4):
    return "\n".join(f"- {str(i)[:200]}" for i in (items or [])[:n])


def phase_2_challenge_generation(state: dict) -> dict:
    meta = state.get("meta_question") or {}
    ctx = (f"{_prior_sharpenings(state)}"
           f"Output purpose: {state.get('output_purpose','')}\n\n"
           f"Current answer:\n{state.get('current_answer','')[:6000]}\n\n"
           f"Dangerous ambiguities:\n{_lines([a.get('term') for a in state.get('top_ambiguities', [])])}\n\n"
           f"Meta-question: {meta.get('higher_level_question','')}\n\n"
           f"Skeptic already raised:\n{_lines(state.get('skeptic_output'))}\n\n"
           f"Source Critic already raised:\n{_lines(state.get('source_critic_output'))}\n\n"
           f"Research:\n{_lines([r.get('results') for r in state.get('research', [])], 3)}\n")
    status = "passed"
    try:
        res = call_claude(model=model_for_role("challenge_generation"),
                          system=load_prompt("albert_persona") + "\n\n" + load_prompt("challenge_generation"),
                          user=ctx, json_schema=schemas.CHALLENGE_GENERATION, purpose="challenge_generation")
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_2 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = _stub(), "failed"
    challenges = res.get("albert_challenges") or []
    if not challenges:
        res, status, challenges = _stub(), "failed", _stub()["albert_challenges"]
    state["albert_challenges"] = challenges
    state["weak_points"] = res.get("weak_points") or []
    state["missing_business_context"] = res.get("missing_business_context") or []
    state["would_survive_leadership"] = bool(res.get("would_survive_leadership", False))
    state["phase_2_status"], state["phase_2_complete"] = status, True
    return state
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat: phase 2 challenge generation (§17+§20 superset, builds on skeptic/source-critic)`.

---

## Task 10: Phase 3 — multi-vote self-critique

**Files:** Create `albert/phases/phase_3_self_critique_audit.py`; Test `tests/test_phase_3_audit.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_phase_3_audit.py
from albert.phases.phase_3_self_critique_audit import phase_3_self_critique_audit

class _Sess:
    """Returns the next queued audit per ask() call (one per vote)."""
    def __init__(self, votes): self.votes = list(votes); self.i = 0
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def ask(self, user, purpose="x"):
        v = self.votes[self.i % len(self.votes)]; self.i += 1
        if v is None: raise RuntimeError("transport")
        return v

def _patch(mp, votes):
    import albert.phases.phase_3_self_critique_audit as m
    mp.setattr(m, "ClaudeSession", lambda **k: _Sess(votes))

def _addr(): return {"round": 1, "verdict": "rework", "weaknesses": [{"challenge_index": 0, "classification": "addressable", "issue": "vague"}]}
def _res():  return {"round": 1, "verdict": "exhausted", "weaknesses": [{"challenge_index": 0, "classification": "residual", "issue": "ask customer"}]}

def test_majority_addressable_is_rework(monkeypatch):
    _patch(monkeypatch, [_addr(), _addr(), _res()])     # 2/3 addressable
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_verdict"] == "REWORK" and out["phase_3_status"] == "passed"
    assert out["phase_3_attempt_count"] == 1

def test_minority_addressable_is_exhausted(monkeypatch):
    _patch(monkeypatch, [_addr(), _res(), _res()])      # only 1/3 addressable
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_verdict"] == "EXHAUSTED"

def test_all_votes_fail_marks_failed_and_exhausted(monkeypatch):
    _patch(monkeypatch, [None, None, None])
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_status"] == "failed" and out["phase_3_verdict"] == "EXHAUSTED"
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
"""Phase 3: MULTI-VOTE adversarial self-critique (N=3). A challenge is ADDRESSABLE only
when >=2 of 3 votes agree — avoids the self-critique paradox where a single same-model
critic hallucinates flaws (spec §5). A degraded run (all votes failed) may not drive rework."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import ClaudeSession
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas

NUM_VOTES = 3


def _has_addressable(audit: dict) -> bool:
    return any(isinstance(w, dict) and w.get("classification") == "addressable"
               for w in (audit.get("weaknesses") or []))


def phase_3_self_critique_audit(state: dict) -> dict:
    state.setdefault("phase_3_rounds", [])
    payload = json.dumps(state["albert_challenges"], ensure_ascii=False)[:20000]
    votes, fail_count = [], 0
    with ClaudeSession(system=load_prompt("self_critique_auditor"),
                       model=model_for_role("self_critique_audit"),
                       schema=schemas.SELF_CRITIQUE_AUDIT, allow_tools=True,
                       max_turns=3, timeout_sec=240) as sess:
        for v in range(1, NUM_VOTES + 1):
            user = (f"Vote {v} of {NUM_VOTES}. Audit these challenges from a fresh, skeptical angle; "
                    f"classify weaknesses; give a verdict.\n\n{payload}\n\n"
                    "Use WebSearch to check whether a challenge is research-backed.")
            try:
                a = sess.ask(user, purpose=f"self_critique_audit_vote_{v}")
                if isinstance(a, list):
                    a = a[0] if (len(a) == 1 and isinstance(a[0], dict)) else {"weaknesses": a, "verdict": "exhausted"}
                if not isinstance(a, dict):
                    a = {"weaknesses": [], "verdict": "exhausted", "_fallback": True}; fail_count += 1
            except VisibilityContractError:
                raise
            except Exception as e:
                sys.stderr.write(f"[WARN] phase_3 vote {v} failed: {type(e).__name__}: {str(e)[:150]}\n")
                a = {"weaknesses": [], "verdict": "exhausted", "_fallback": True}; fail_count += 1
            votes.append(a)

    state["phase_3_rounds"].append({"votes": votes})
    is_degraded = fail_count >= NUM_VOTES                      # all votes failed -> degraded
    addressable_votes = sum(1 for a in votes if not a.get("_fallback") and _has_addressable(a))
    # Majority of real votes say addressable -> REWORK; else EXHAUSTED. Degraded -> never rework.
    verdict = "REWORK" if (not is_degraded and addressable_votes >= 2) else "EXHAUSTED"
    state["phase_3_verdict"] = verdict
    state["phase_3_status"] = "failed" if is_degraded else "passed"
    state["phase_3_attempt_count"] = state.get("phase_3_attempt_count", 0) + 1
    # Carry the union of addressable sharpenings (from real votes) for phase 2 rework feedback.
    merged = [w for a in votes if not a.get("_fallback")
              for w in (a.get("weaknesses") or []) if w.get("classification") == "addressable"]
    state["phase_3_rounds"][-1]["weaknesses"] = merged
    state["phase_3_complete"] = True
    return state
```

> Note: Phase 2 reads `phase_3_rounds[-1]["weaknesses"]` for rework feedback (Task 9 `_prior_sharpenings`), which this phase populates with the merged addressable set.

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat: phase 3 multi-vote self-critique (avoids self-critique paradox)`.

---

## Task 11: Phase 4 — signals · action · gate

**Files:** Create `albert/phases/phase_4_signals_action_gate.py`; Test `tests/test_phase_4_signals.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_phase_4_signals.py
from albert.phases.phase_4_signals_action_gate import phase_4_signals_action_gate

def _resp(action="synthesize"):
    return {"premature_end_atoms": {"open_high_impact_challenges": 2, "new_info_rate": "high",
            "challenge_map_mostly_classified": False, "unresolved_are_human_data_decision_only": False,
            "meta_question_search_found_new_high_impact_angle": True},
            "drift_atoms": {"current_focus_in_original_high_value_set": True, "high_value_branch_ignored": False},
            "recommended_next_probe": [{"probe": "p", "why": "w", "impact": "high", "answerability": "low"}],
            "missing_evidence": [{"item": "x", "who_can_answer": "public"}],
            "questions_albert_would_ask": ["q?"], "proposed_next_action": action, "rationale": "r",
            "decision_gate": {"can_decide_now": [], "cannot_decide": ["price"], "owners": []},
            "reproducible_judgment": "rj"}

def test_level_from_atoms_and_action_vetoed(monkeypatch):
    import albert.phases.phase_4_signals_action_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp("synthesize"))
    out = phase_4_signals_action_gate({"current_answer": "x", "albert_challenges": [],
        "research_state": {"new_info_rate": "high"}})
    assert out["premature_end_risk"]["level"] == "high"
    assert out["premature_end_risk"]["grounded_in"] == "research_state"
    assert out["recommended_next_action"] == "continue_research"   # synthesize vetoed by high premature_end
    assert out["recommended_next_probe"][0]["priority"] == 1
    assert out["phase_4_status"] == "passed"

def test_inferred_when_no_telemetry(monkeypatch):
    import albert.phases.phase_4_signals_action_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp("branch"))
    out = phase_4_signals_action_gate({"current_answer": "x", "albert_challenges": [], "research_state": {}})
    assert out["premature_end_risk"]["grounded_in"] == "inferred"
    assert out["premature_end_risk"]["low_confidence"] is True
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**

```python
"""Phase 4 (bones 7,9,12): LLM produces atoms + a proposed action; signals.py computes the
risk levels and vetoes an inconsistent action."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert.signals import (premature_end_level, drift_level, rank_next_probe,
                            build_risk, enforce_action_consistency)

_STUB = {"premature_end_atoms": {"open_high_impact_challenges": 1, "new_info_rate": "unknown",
         "challenge_map_mostly_classified": False, "unresolved_are_human_data_decision_only": False,
         "meta_question_search_found_new_high_impact_angle": False},
         "drift_atoms": {}, "recommended_next_probe": [], "missing_evidence": [],
         "questions_albert_would_ask": [], "proposed_next_action": "continue_research", "rationale": "(LLM unavailable)",
         "decision_gate": {"can_decide_now": [], "cannot_decide": ["(LLM unavailable)"], "owners": []},
         "reproducible_judgment": ""}


def phase_4_signals_action_gate(state: dict) -> dict:
    rs = state.get("research_state") or {}
    ctx = (f"Current answer:\n{state.get('current_answer','')[:3000]}\n\n"
           f"Challenges:\n{json.dumps(state.get('albert_challenges', []), ensure_ascii=False)[:10000]}\n\n"
           f"research_state:\n{json.dumps(rs, ensure_ascii=False)[:3000]}\n"
           f"readiness_scores:\n{json.dumps(state.get('readiness_scores', {}), ensure_ascii=False)[:1000]}\n")
    status = "passed"
    try:
        res = call_claude(model=model_for_role("signals_action_gate"),
                          system=load_prompt("signals_action_gate"), user=ctx,
                          json_schema=schemas.SIGNALS_ACTION_GATE, purpose="signals_action_gate")
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_4 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = dict(_STUB), "failed"

    pe_atoms = res.get("premature_end_atoms") or _STUB["premature_end_atoms"]
    dr_atoms = res.get("drift_atoms") or {}
    pe_level, dr_level = premature_end_level(pe_atoms), drift_level(dr_atoms)
    state["premature_end_risk"] = build_risk(pe_level, pe_atoms, rs)
    state["research_drift_risk"] = build_risk(dr_level, dr_atoms, rs)
    state["recommended_next_probe"] = rank_next_probe(res.get("recommended_next_probe") or [])
    state["missing_evidence"] = res.get("missing_evidence") or []
    state["questions_albert_would_ask"] = res.get("questions_albert_would_ask") or []
    state["recommended_next_action"] = enforce_action_consistency(
        res.get("proposed_next_action", "continue_research"), pe_level, dr_level, state["missing_evidence"])
    state["rationale"] = res.get("rationale") or ""
    state["decision_gate"] = res.get("decision_gate") or dict(_STUB["decision_gate"])
    state["reproducible_judgment"] = res.get("reproducible_judgment") or ""
    state["phase_4_status"], state["phase_4_complete"] = status, True
    return state
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat: phase 4 signals + action-consistency + gate`.

---

## Task 12: `albert/render.py` + degraded guard

**Files:** Create `albert/render.py`, `templates/albert_report_template.md`; Test `tests/test_render_degraded_guard.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_render_degraded_guard.py
import pytest
from albert.render import enforce_degraded_guard, build_challenge
from albert.errors import DegradedEmissionError

def test_failed_green_raises():
    with pytest.raises(DegradedEmissionError):
        enforce_degraded_guard(True, "green")

def test_allowed():
    enforce_degraded_guard(True, "red"); enforce_degraded_guard(False, "green")

def test_build_has_auditresult_fields():
    c = build_challenge({"verdict": "exhausted", "albert_challenges": [], "weak_points": [],
        "premature_end_risk": {"level": "low", "grounded_in": "inferred"},
        "research_drift_risk": {"level": "low", "grounded_in": "inferred"},
        "recommended_next_action": "synthesize", "rationale": "r", "degraded": False, "run_status": "passed"})
    for k in ("verdict", "albert_challenges", "premature_end_risk", "recommended_next_action", "rationale", "degraded"):
        assert k in c
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement `albert/render.py`**

```python
"""Assemble the albert_challenge contract (AuditResult-aligned), degraded guard, markdown report."""
import json
from pathlib import Path
from albert.errors import DegradedEmissionError

_LIGHT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def enforce_degraded_guard(degraded: bool, light: str) -> None:
    if degraded and light == "green":
        raise DegradedEmissionError("green light on a degraded run is forbidden", "degraded_green")


def build_challenge(state: dict) -> dict:
    return {
        "verdict": state.get("verdict", "rework"),
        "audited_answer": state.get("current_answer", ""),
        "would_survive_leadership": bool(state.get("would_survive_leadership", False)),
        "top_ambiguities": state.get("top_ambiguities", []),
        "albert_challenges": state.get("albert_challenges", []),
        "weak_points": state.get("weak_points", []),
        "missing_business_context": state.get("missing_business_context", []),
        "missing_evidence": state.get("missing_evidence", []),
        "questions_albert_would_ask": state.get("questions_albert_would_ask", []),
        "premature_end_risk": state.get("premature_end_risk", {"level": "low", "grounded_in": "inferred"}),
        "research_drift_risk": state.get("research_drift_risk", {"level": "low", "grounded_in": "inferred"}),
        "recommended_next_probe": state.get("recommended_next_probe", []),
        "recommended_next_action": state.get("recommended_next_action", "continue_research"),
        "rationale": state.get("rationale", ""),
        "decision_gate": state.get("decision_gate", {"can_decide_now": [], "cannot_decide": [], "owners": []}),
        "readiness_score_delta": int(state.get("readiness_score_delta", 0)),
        "reproducible_judgment": state.get("reproducible_judgment", ""),
        "degraded": bool(state.get("degraded", False)),
        "run_status": state.get("run_status", "failed"),
        "verdict_standalone": state.get("verdict_standalone", "產品定義不完整"),
        "light": state.get("light", "red"),
    }


def write_challenge_json(state: dict, run_dir: Path) -> str:
    p = Path(run_dir) / "albert_challenge.json"
    p.write_text(json.dumps(build_challenge(state), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def render_report(state: dict) -> str:
    c = build_challenge(state)
    L = [f"# Albert Review — {state.get('proposal', {}).get('title', '(current answer)')}", "",
         f"**Audit verdict:** {c['verdict']} · would_survive_leadership={c['would_survive_leadership']} · "
         f"degraded={c['degraded']}", "",
         f"**Recommended next action:** `{c['recommended_next_action']}` — {c['rationale']}", "",
         f"**premature_end:** {c['premature_end_risk'].get('level')} "
         f"(grounded_in={c['premature_end_risk'].get('grounded_in')}) · "
         f"**drift:** {c['research_drift_risk'].get('level')}", "",
         f"**Standalone:** {c['verdict_standalone']} {_LIGHT.get(c['light'],'')} · delta {c['readiness_score_delta']}",
         "", "## 最危險的 3 個模糊點"]
    L += [f"- **{a.get('term','')}** — {a.get('why_dangerous','')} → {a.get('precise_question','')}"
          for a in c["top_ambiguities"]]
    L += ["", "## 靈魂拷問 (albert_challenges)"]
    for i, q in enumerate(c["albert_challenges"], 1):
        L.append(f"{i}. [{q.get('status','')}/sev={q.get('severity','')}/{q.get('generator','')}] "
                 f"{q.get('challenge','')}  ↳ {q.get('next_action','')}")
    L += ["", "## Weak points"] + [f"- {w}" for w in c["weak_points"]]
    L += ["", "## Recommended next probe"]
    L += [f"{p.get('priority','')}. [{p.get('kind','')}] {p.get('probe','')} — {p.get('why','')}"
          for p in c["recommended_next_probe"]]
    L += ["", "## 可複用判斷", c["reproducible_judgment"] or "(none)"]
    return "\n".join(L)


def write_report(state: dict, run_dir: Path) -> str:
    p = Path(run_dir) / "albert_review.md"
    p.write_text(render_report(state), encoding="utf-8")
    return str(p)
```

- [ ] **Step 4: Write `templates/albert_report_template.md`** (reference layout: title, audit verdict, recommended next action + rationale, risk lines, ambiguities, challenges, weak points, next probe, reproducible judgment).
- [ ] **Step 5: Run → PASS. Step 6: Commit** `feat: render + degraded guard (AuditResult-aligned)`.

---

## Task 13: `albert/cockpit_contract.py` + R17 contract test

**Files:** Create `albert/cockpit_contract.py`, `docs/albert-cockpit-mapping.md`; Test `tests/test_cockpit_contract.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_cockpit_contract.py
from albert.cockpit_contract import to_audit_result
from albert.state import DECISIONS, AUDIT_VERDICTS, RISK_LEVELS, CHALLENGE_STATUSES

def _golden():
    return {"verdict": "exhausted",
        "albert_challenges": [{"challenge": "why win?", "why_albert_would_ask": "parity",
            "current_answer": "", "status": "needs_bu_judgment", "confidence": "low",
            "missing_info": "ROI", "blocking_owner": "PM", "next_action": "get ROI",
            "meeting_ready_response": "..."}],
        "weak_points": ["no ROI"], "missing_business_context": ["TAM"],
        "missing_evidence": [{"item": "roadmap", "who_can_answer": "public"}],
        "questions_albert_would_ask": ["why win?"],
        "premature_end_risk": {"level": "high"}, "research_drift_risk": {"level": "low"},
        "recommended_next_probe": [{"probe": "p", "why": "w", "priority": 1}],
        "recommended_next_action": "continue_research", "rationale": "still open",
        "readiness_score_delta": -1, "degraded": False}

def test_auditresult_fields_complete():
    ar = to_audit_result(_golden())["audit_result"]
    for k in ("verdict", "challenges", "weak_points", "premature_end_risk",
              "research_drift_risk", "recommended_next_action", "rationale", "degraded"):
        assert k in ar

def test_enums_valid():
    ar = to_audit_result(_golden())["audit_result"]
    assert ar["verdict"] in AUDIT_VERDICTS
    assert ar["recommended_next_action"] in DECISIONS
    assert ar["premature_end_risk"] in RISK_LEVELS
    assert isinstance(ar["degraded"], bool)
    for ch in ar["challenges"]:
        assert ch["status"] in CHALLENGE_STATUSES

def test_weak_points_are_strings():
    ar = to_audit_result(_golden())["audit_result"]
    assert all(isinstance(w, str) for w in ar["weak_points"])

def test_enrichment_present():
    enr = to_audit_result(_golden())["enrichment"]
    for k in ("missing_business_context", "questions_albert_would_ask",
              "recommended_next_probe", "readiness_score_delta"):
        assert k in enr
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement `albert/cockpit_contract.py`**

```python
"""Reference mapping: albert_challenge.json -> cockpit AuditResult (+ enrichment for the
gap-audit A2 fields the cockpit's AuditResult does not yet carry). Proves the R17 seam.
The cockpit owns the production adapter; this is the producer-side proof."""
from __future__ import annotations

_CHALLENGE_FIELDS = ["challenge", "why_albert_would_ask", "current_answer", "status",
                     "confidence", "evidence_refs", "missing_info", "blocking_owner",
                     "next_action", "meeting_ready_response"]


def _entry(ch: dict) -> dict:
    e = {k: ch.get(k, "") for k in _CHALLENGE_FIELDS}
    e["evidence_refs"] = ch.get("evidence_refs", [])
    return e


def to_audit_result(challenge: dict) -> dict:
    return {
        "audit_result": {                                   # the cockpit's AuditResult (load-bearing)
            "verdict": challenge.get("verdict", "rework"),
            "challenges": [_entry(c) for c in challenge.get("albert_challenges", [])],
            "weak_points": [w if isinstance(w, str) else str(w) for w in challenge.get("weak_points", [])],
            "premature_end_risk": (challenge.get("premature_end_risk") or {}).get("level", "low"),
            "research_drift_risk": (challenge.get("research_drift_risk") or {}).get("level", "low"),
            "recommended_next_action": challenge.get("recommended_next_action"),
            "rationale": challenge.get("rationale", ""),
            "degraded": bool(challenge.get("degraded", False)),
        },
        "enrichment": {                                     # gap-audit A2 (cockpit will add these fields)
            "missing_business_context": challenge.get("missing_business_context", []),
            "questions_albert_would_ask": challenge.get("questions_albert_would_ask", []),
            "recommended_next_probe": challenge.get("recommended_next_probe", []),
            "readiness_score_delta": challenge.get("readiness_score_delta", 0),
            "premature_end_atoms": (challenge.get("premature_end_risk") or {}).get("atoms", {}),
            "grounded_in": (challenge.get("premature_end_risk") or {}).get("grounded_in", "inferred"),
        },
    }
```

- [ ] **Step 4: Write `docs/albert-cockpit-mapping.md`** — the mapping table from spec §6 (Albert field → cockpit `AuditResult` field + enrichment), noting `cockpit_contract.to_audit_result` is the executable reference and this test is the R17 anchor.
- [ ] **Step 5: Run → PASS. Step 6: Commit** `feat: cockpit_contract -> AuditResult + R17 contract test + mapping doc`.

---

## Task 14: `albert/email_delivery.py` + Phase 5 assemble (verdict + degraded)

**Files:** Create `albert/email_delivery.py`, `albert/phases/phase_5_assemble_render.py`; Test `tests/test_email_delivery.py`, `tests/test_phase_5_assemble.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_email_delivery.py
import albert.email_delivery as ed
def test_sent(monkeypatch, tmp_path):
    p = tmp_path/"r.md"; p.write_text("b", encoding="utf-8")
    monkeypatch.setattr(ed, "_send_via_outlook", lambda to, subject, body, cc: None)
    assert ed.send_email(to="a@b.com", subject="s", body_path=str(p)) == "sent"
def test_skipped(tmp_path):
    p = tmp_path/"r.md"; p.write_text("b", encoding="utf-8")
    assert ed.send_email(to=None, subject="s", body_path=str(p)) == "skipped"
```

```python
# tests/test_phase_5_assemble.py
from albert.phases.phase_5_assemble_render import phase_5_assemble_render

def _state(tmp_path, statuses, verdict="exhausted"):
    s = {"run_dir": str(tmp_path), "run_id": "r", "mode": "standalone", "proposal": {"title": "T"},
         "current_answer": "a", "top_ambiguities": [], "albert_challenges": [], "weak_points": [],
         "missing_business_context": [], "missing_evidence": [], "questions_albert_would_ask": [],
         "recommended_next_probe": [], "recommended_next_action": "synthesize", "rationale": "r",
         "premature_end_risk": {"level": "low", "grounded_in": "inferred"},
         "research_drift_risk": {"level": "low", "grounded_in": "inferred"},
         "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
         "reproducible_judgment": "rj", "phase_3_verdict": "EXHAUSTED"}
    s.update(statuses); return s

def test_passed_sets_verdict_and_not_degraded(tmp_path, monkeypatch):
    import albert.phases.phase_5_assemble_render as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"verdict_standalone": "可推進", "light": "green", "readiness_score_delta": 1})
    monkeypatch.setattr(m, "send_email", lambda **k: "skipped")
    out = phase_5_assemble_render(_state(tmp_path, {f"phase_{i}_status": "passed" for i in range(5)}))
    assert out["degraded"] is False and out["verdict"] in ("continue", "exhausted", "rework")
    assert out["light"] == "green" and out["challenge_json_path"] and out["report_path"]

def test_failed_phase_degrades_and_downgrades_green(tmp_path, monkeypatch):
    import albert.phases.phase_5_assemble_render as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"verdict_standalone": "可推進", "light": "green", "readiness_score_delta": 2})
    monkeypatch.setattr(m, "send_email", lambda **k: "skipped")
    out = phase_5_assemble_render(_state(tmp_path, {"phase_0_status": "passed", "phase_1_status": "failed",
        "phase_2_status": "passed", "phase_3_status": "passed", "phase_4_status": "passed"}))
    assert out["degraded"] is True and out["light"] != "green"
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement `albert/email_delivery.py`** (Outlook COM, best-effort, returns status; identical to the sibling pattern):

```python
"""Outlook COM email (standalone only). Best-effort: returns a status, never raises."""
import json
from pathlib import Path
_CFG = Path.home() / ".claude" / "email.json"


def _load_cfg() -> dict:
    try:
        return json.loads(_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _send_via_outlook(to: str, subject: str, body: str, cc: str | None) -> None:
    import win32com.client
    outlook = win32com.client.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)
    mail.To = to
    if cc:
        mail.CC = cc
    mail.Subject = subject
    mail.Body = body
    mail.Send()


def send_email(to: str | None, subject: str, body_path: str, cc: str | None = None) -> str:
    if not to:
        return "skipped"
    body = Path(body_path).read_text(encoding="utf-8")
    _send_via_outlook(to, subject, body, cc or _load_cfg().get("operator_email"))
    return "sent"
```

- [ ] **Step 4: Implement `albert/phases/phase_5_assemble_render.py`**

```python
"""Phase 5: compute AuditVerdict + degraded, standalone verdict+light (degraded guard),
assemble the AuditResult-aligned contract, render + email."""
import sys
from pathlib import Path
from albert.errors import VisibilityContractError, DegradedEmissionError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert.render import enforce_degraded_guard, write_challenge_json, write_report
from albert.email_delivery import send_email

_STATUS_KEYS = [f"phase_{i}_status" for i in range(5)]


def _audit_verdict(state: dict, degraded: bool) -> str:
    """Map the run to the cockpit AuditVerdict {continue, exhausted, rework}.
    rework if the self-critique still wanted rework or any dangerous ambiguity is unresolved-ish;
    exhausted if the loop exhausted cleanly; continue if premature_end is high (more research warranted)."""
    if state.get("phase_3_verdict") == "REWORK":
        return "rework"
    if (state.get("premature_end_risk", {}) or {}).get("level") == "high":
        return "continue"
    return "exhausted"


def phase_5_assemble_render(state: dict) -> dict:
    degraded = any(state.get(k) == "failed" for k in _STATUS_KEYS)
    state["degraded"] = degraded
    state["run_status"] = "failed" if degraded else "passed"
    state["verdict"] = _audit_verdict(state, degraded)

    ctx = (f"Ambiguities: {state.get('top_ambiguities')}\nChallenges: {len(state.get('albert_challenges', []))}\n"
           f"premature_end: {state.get('premature_end_risk', {}).get('level')}\n"
           f"missing_evidence: {state.get('missing_evidence')}\n")
    try:
        v = call_claude(model=model_for_role("verdict_render"), system=load_prompt("verdict_render"),
                        user=ctx, json_schema=schemas.VERDICT, purpose="verdict_render")
        vs, light, delta = v.get("verdict_standalone", "要補證據"), v.get("light", "yellow"), int(v.get("readiness_score_delta", 0))
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_5 verdict failed: {type(e).__name__}: {str(e)[:200]}; refuse\n")
        vs, light, delta, degraded = "產品定義不完整", "red", -2, True
        state["degraded"], state["run_status"] = True, "failed"

    try:
        enforce_degraded_guard(degraded, light)
    except DegradedEmissionError:
        light = "red"
        if vs == "可推進":
            vs = "要補證據"

    state["verdict_standalone"], state["light"], state["readiness_score_delta"] = vs, light, delta
    run_dir = Path(state["run_dir"])
    state["challenge_json_path"] = write_challenge_json(state, run_dir)
    state["report_path"] = write_report(state, run_dir)

    if state.get("mode") == "standalone" and state.get("user_email"):
        try:
            state["email_delivery_result"] = send_email(to=state["user_email"],
                subject=f"[Albert] {vs} — {state['proposal'].get('title','review')}", body_path=state["report_path"])
        except Exception as e:
            state["email_delivery_result"] = "failed"
            state["email_delivery_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    state["phase_5_complete"] = True
    return state
```

- [ ] **Step 5: Run → PASS. Step 6: Commit** `feat: phase 5 assemble (AuditVerdict + degraded) + render + email`.

---

## Task 15: `albert/graph.py` + topology & exhaustion-loop tests

**Files:** Create `albert/graph.py`; Test `tests/test_graph_topology.py`, `tests/test_self_critique_loop.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_graph_topology.py
from albert.graph import build_graph, _route_after_audit, _max_rework
def test_compiles(): assert build_graph() is not None
def test_rework_under_cap(monkeypatch):
    monkeypatch.delenv("ALBERT_MAX_REWORK", raising=False)
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}) == "phase_2_challenge_generation"
def test_rework_over_cap(monkeypatch):
    monkeypatch.setenv("ALBERT_MAX_REWORK", "2")
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 3}) == "phase_4_signals_action_gate"
def test_exhausted(): assert _route_after_audit({"phase_3_verdict": "EXHAUSTED", "phase_3_attempt_count": 1}) == "phase_4_signals_action_gate"
def test_cap_zero(monkeypatch):
    monkeypatch.setenv("ALBERT_MAX_REWORK", "0")
    assert _max_rework() == 0
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}) == "phase_4_signals_action_gate"
```

```python
# tests/test_self_critique_loop.py
import tempfile
from albert.graph import build_graph

def test_loop_terminates(monkeypatch):
    import albert.phases.phase_0_intake_grounding as p0, albert.phases.phase_1_ambiguity_hunt as p1
    import albert.phases.phase_2_challenge_generation as p2, albert.phases.phase_3_self_critique_audit as p3
    import albert.phases.phase_4_signals_action_gate as p4, albert.phases.phase_5_assemble_render as p5
    monkeypatch.setenv("ALBERT_MAX_REWORK", "2")
    monkeypatch.setattr(p0, "call_claude", lambda **k: {"queries": []} if k["purpose"]=="intake_grounding" else {"higher_level_question":"h","wave2_queries":[]})
    monkeypatch.setattr(p0, "websearch", lambda q: {"query": q, "results": ""})
    monkeypatch.setattr(p1, "call_claude", lambda **k: {"top_ambiguities":[{"term":"t","why_dangerous":"w","precise_question":"p"}]*3})
    monkeypatch.setattr(p2, "call_claude", lambda **k: {"albert_challenges":[{"challenge":"x","why_albert_would_ask":"y","status":"blocked","severity":"high","current_answer_strength":"weak","generator":"winning","bone":2}],"weak_points":[],"missing_business_context":[],"would_survive_leadership":False})
    calls = {"n": 0}
    class _S:
        def __init__(self,**k): pass
        def __enter__(self): return self
        def __exit__(self,*a): return False
        def ask(self,user,purpose="x"):
            # 2 addressable votes on attempts 1-2 (rework), all-residual on attempt 3 (exhausted)
            calls["n"] += 1
            attempt = (calls["n"] - 1) // 3 + 1
            cls = "addressable" if attempt < 3 else "residual"
            return {"round": attempt, "weaknesses": [{"classification": cls, "issue": "i"}], "verdict": "rework" if attempt<3 else "exhausted"}
    monkeypatch.setattr(p3, "ClaudeSession", lambda **k: _S())
    monkeypatch.setattr(p4, "call_claude", lambda **k: {"premature_end_atoms":{"open_high_impact_challenges":0,"new_info_rate":"low"},"drift_atoms":{},"recommended_next_probe":[],"missing_evidence":[],"questions_albert_would_ask":[],"proposed_next_action":"synthesize","rationale":"r","decision_gate":{"can_decide_now":[],"cannot_decide":[],"owners":[]},"reproducible_judgment":"rj"})
    monkeypatch.setattr(p5, "call_claude", lambda **k: {"verdict_standalone":"可推進","light":"green","readiness_score_delta":1})
    monkeypatch.setattr(p5, "send_email", lambda **k: "skipped")
    g = build_graph()
    state = {"albert_input": {"current_answer": "a", "mode": "standalone", "proposal": {}, "research_state": {}}, "run_dir": tempfile.mkdtemp(), "run_id": "r", "mode": "standalone"}
    final = g.invoke(state, config={"configurable": {"thread_id": "t", "recursion_limit": 100}})
    assert final["phase_5_complete"] is True and final["phase_3_attempt_count"] == 3
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement `albert/graph.py`**

```python
"""LangGraph StateGraph for the Albert Thought Agent FSM.
START -> p0 -> p1 -> p2 -> p3 ; p3 --[REWORK & attempt<=cap]--> p2 ; --[else]--> p4 -> p5 -> END
"""
import os
from functools import wraps
from langgraph.graph import StateGraph, START, END
from langgraph.errors import GraphInterrupt
from albert.state import AlbertState
from albert.phases.phase_0_intake_grounding import phase_0_intake_grounding
from albert.phases.phase_1_ambiguity_hunt import phase_1_ambiguity_hunt
from albert.phases.phase_2_challenge_generation import phase_2_challenge_generation
from albert.phases.phase_3_self_critique_audit import phase_3_self_critique_audit
from albert.phases.phase_4_signals_action_gate import phase_4_signals_action_gate
from albert.phases.phase_5_assemble_render import phase_5_assemble_render


def _max_rework() -> int:
    try:
        return max(0, int(os.environ.get("ALBERT_MAX_REWORK", "2")))
    except (TypeError, ValueError):
        return 2


def _route_after_audit(state: dict) -> str:
    if state.get("phase_3_verdict") == "REWORK" and state.get("phase_3_attempt_count", 0) <= _max_rework():
        return "phase_2_challenge_generation"
    return "phase_4_signals_action_gate"


def _wrap(name, fn):
    @wraps(fn)
    def w(state):
        from albert import progress as _p
        from albert.stage_summary import emit_phase_error, emit_phase_start_summary, emit_stage_summary
        emit_phase_start_summary(name, state)
        _p.phase_start(name, {"state_keys": list(state.keys())[:20]})
        try:
            result = fn(state)
            if not isinstance(result, dict):
                raise TypeError(f"{name} must return dict, got {type(result).__name__}")
            merged = dict(state); merged.update(result)
            result.update(emit_stage_summary(name, merged))
            _p.phase_end(name, {"ok": True})
            return result
        except GraphInterrupt:
            _p.emit(name, "phase_interrupt", {"reason": "interrupt"}); raise
        except Exception as e:
            emit_phase_error(name, state, e)
            _p.emit(name, "phase_error", {"error": type(e).__name__, "message": str(e)[:300]}); raise
    return w


def build_graph(checkpointer=None):
    g = StateGraph(AlbertState)
    for nm, fn in [("phase_0_intake_grounding", phase_0_intake_grounding),
                   ("phase_1_ambiguity_hunt", phase_1_ambiguity_hunt),
                   ("phase_2_challenge_generation", phase_2_challenge_generation),
                   ("phase_3_self_critique_audit", phase_3_self_critique_audit),
                   ("phase_4_signals_action_gate", phase_4_signals_action_gate),
                   ("phase_5_assemble_render", phase_5_assemble_render)]:
        g.add_node(nm, _wrap(nm, fn))
    g.add_edge(START, "phase_0_intake_grounding")
    g.add_edge("phase_0_intake_grounding", "phase_1_ambiguity_hunt")
    g.add_edge("phase_1_ambiguity_hunt", "phase_2_challenge_generation")
    g.add_edge("phase_2_challenge_generation", "phase_3_self_critique_audit")
    g.add_conditional_edges("phase_3_self_critique_audit", _route_after_audit,
        {"phase_2_challenge_generation": "phase_2_challenge_generation",
         "phase_4_signals_action_gate": "phase_4_signals_action_gate"})
    g.add_edge("phase_4_signals_action_gate", "phase_5_assemble_render")
    g.add_edge("phase_5_assemble_render", END)
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat: FSM graph with exhaustion conditional edge`.

---

## Task 16: `run_albert.py` + SKILL.md + README + symlink + smoke

**Files:** Create `run_albert.py`, `SKILL.md`, `README.md`.

- [ ] **Step 1: Implement `run_albert.py`** (CLI: standalone + cockpit `--json-out` + `--resume`/`--gc`/`--dry-run`):

```python
"""CLI entry point for the Albert Thought Agent FSM."""
import argparse, shutil, sys, time, uuid
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from albert.graph import build_graph
from albert.input_adapter import build_input

RUNS_DIR = Path(__file__).parent / "runs"
RETENTION_DAYS = 30


def main():
    ap = argparse.ArgumentParser(prog="run_albert")
    ap.add_argument("proposal", nargs="?")
    ap.add_argument("--input", dest="input_json")
    ap.add_argument("--json-out", action="store_true")
    ap.add_argument("--resume", dest="resume_id")
    ap.add_argument("--gc", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--user-email")
    args = ap.parse_args()
    if args.gc:
        _gc(); return 0
    if not args.proposal and not args.input_json and not args.resume_id:
        ap.error("a proposal, --input, or --resume is required")
    run_id = args.resume_id or f"run-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        print(f"Would invoke Albert with run_id={run_id}"); return 0
    from albert import progress as _p
    _p.init(run_dir)
    try:
        from albert import heartbeat as _hb
        _hb.start(run_dir, run_id)
    except Exception as e:
        sys.stderr.write(f"[run_albert] WARN heartbeat: {e}\n")
    with SqliteSaver.from_conn_string(str(run_dir / "checkpoint.db")) as cp:
        graph = build_graph(checkpointer=cp)
        config = {"configurable": {"thread_id": run_id, "recursion_limit": 100}}
        if args.resume_id:
            initial = None
        else:
            ai = build_input(raw_text=args.proposal, input_json=args.input_json)
            initial = {"albert_input": ai, "mode": ai["mode"], "run_id": run_id,
                       "run_dir": str(run_dir), "user_email": args.user_email}
        try:
            final = graph.invoke(initial, config=config)
        except Exception as exc:
            sys.stderr.write(f"[Albert] Run failed: {type(exc).__name__}: {str(exc)[:300]}\n"); return 1
    if not final.get("phase_5_complete"):
        sys.stderr.write(f"Run incomplete. Inspect {run_dir}\n"); return 2
    if args.json_out:
        print(final.get("challenge_json_path", ""))
    else:
        sys.stderr.write(f"[Albert] verdict={final.get('verdict')} next={final.get('recommended_next_action')} "
                         f"premature_end={final.get('premature_end_risk',{}).get('level')} "
                         f"standalone={final.get('verdict_standalone')}({final.get('light')})\n")
        print(final.get("report_path", ""))
    return 0


def _gc():
    cutoff = time.time() - RETENTION_DAYS * 86400
    if RUNS_DIR.exists():
        for d in RUNS_DIR.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write `SKILL.md`**

```markdown
---
name: skill-cn5-i-am-albert
description: Use when auditing a product/architecture answer or proposal from a high-standard BU-head war-room perspective — simulating how Albert would challenge a current answer to force decision quality, not summarize. Acts as the cockpit's Albert Thought Agent (returns an AuditResult-aligned contract). Triggers on Albert review, war-room audit, 靈魂拷問, would this survive leadership, winning thesis, durability/moat, decision gate, premature stop risk, research drift, recommended next action, will-it-win, readiness audit. LangGraph FSM — intake+meta-research, ambiguity hunt, challenge generation, multi-vote self-critique exhaustion loop, rule-grounded stop/drift signals + recommended next action.
execution_mode: both
---

# Albert — Albert Thought Agent (LangGraph-driven)

Albert audits a CURRENT ANSWER: would it survive a leadership challenge, where is it weak,
what to probe next, and what should the team do next. He does not praise or summarize.

## Invocation

Cockpit (programmatic — prints the challenge JSON path):

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py --input albert_input.json --json-out

Standalone (review a proposal → report + email):

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py "<proposal text or file>" --user-email you@example.com

Flags: `--resume <run_id>`, `--gc`, `--dry-run`. Env: `ALBERT_MAX_REWORK` (default 2), `ALBERT_FAST_MODEL`.

## Output & contract

`albert_challenge.json` (schema `schemas/albert_challenge.schema.json`) maps to the cockpit's
`AuditResult`: verdict (continue|exhausted|rework), albert_challenges (§17 entry, 8-value status),
weak_points, premature_end_risk / research_drift_risk (rule-grounded), recommended_next_action
(COS Decision enum), rationale, degraded. Mapping in `docs/albert-cockpit-mapping.md`;
`albert/cockpit_contract.py` + `tests/test_cockpit_contract.py` prove the seam (R17). Do not change
the schemas without re-running that test + the cockpit's integration test.
```

- [ ] **Step 3: Write `README.md`** — Albert Thought Agent for the CN5 cockpit; 12 bones (link spec); invocation; FSM + multi-vote exhaustion loop; rule-grounded signals + recommended_next_action; env vars; R17 seam artifacts.
- [ ] **Step 4: Smoke + full suite** — `py -3 run_albert.py --dry-run "test"` (exit 0); `py -3 -m pytest tests/ -v` (all PASS).
- [ ] **Step 5: Symlink** — `New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\skill-cn5-i-am-albert" -Target "D:\D-claude\skill-cn5-i-am-albert"`.
- [ ] **Step 6: Commit** `feat: run_albert CLI + SKILL.md + README; symlink + green suite`.

---

## Self-Review (completed)

**Spec coverage (v0.4.1):**
- §1 unified pipeline / dual mode / job-separation (recommend, not decide) → Tasks 7, 11 (`enforce_action_consistency`), 16.
- §2 12 bones + durability soul-grade → Task 6.
- §3 enriched §20 input (meeting_context, output_purpose, readiness_scores, recent_research_actions, skeptic/source-critic output, research_state) → Tasks 4, 7; loop-position build-on → Task 9.
- §4 AuditResult-aligned output (verdict/recommended_next_action/rationale/degraded; weak_points list[str]; challenge severity+current_answer_strength) → Tasks 3, 4, 12; rule-grounded signals + action consistency → Task 5, 11.
- §5 phases 0-5 + conditional edge; multi-vote Phase 3 → Tasks 7-15; meta vs object research → Task 7.
- §6 seam → Albert AuditResult (Task 13: `to_audit_result`, mapping doc, R17 contract test).
- §7 invocation/env → Tasks 16, 2. §8 layout → all. §9 testing → every task TDD incl. test_signals_grounding, test_action_consistency, test_cockpit_contract, test_render_degraded_guard, test_self_critique_loop.
- §10 enums frozen (continue|exhausted|rework etc.) → Tasks 3, 4 use them verbatim.

**Placeholder scan:** Task 16 Step 3 (README) describes contents (prose doc, acceptable). All code steps complete.

**Type consistency:** enums (`DECISIONS`/`AUDIT_VERDICTS`/`RISK_LEVELS`/`CHALLENGE_STATUSES`), schema names (`SIGNALS_ACTION_GATE`/`CHALLENGE_GENERATION`/`SELF_CRITIQUE_AUDIT`/`VERDICT`/`ALBERT_CHALLENGE`/`ALBERT_INPUT`/`SEARCH_REFLECTION`/`AMBIGUITY_HUNT`), `signals.py` fns (`premature_end_level`/`drift_level`/`rank_next_probe`/`build_risk`/`grounding_of`/`enforce_action_consistency`), node names (`phase_4_signals_action_gate`), `to_audit_result` keys (`audit_result`/`enrichment`), `phase_3_rounds[-1]["weaknesses"]` contract between Task 10 (writer) and Task 9 (reader) — all consistent.
```
