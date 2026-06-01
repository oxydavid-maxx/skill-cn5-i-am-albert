# Albert Soul Implementation Plan (v0.3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `skill-cn5-i-am-albert` — a LangGraph FSM **Albert Thought Agent** that audits a *current answer* inside a research loop, emitting challenges + weak points + rule-grounded stop/continue/drift signals that the CN5 cockpit consumes.

**Architecture:** Six-phase LangGraph `StateGraph` with one conditional edge (Phase 3 self-critique → Phase 2 regenerate) implementing an exhaustion loop. Loop signals (`premature_end_risk` / `research_drift_risk` / `recommended_next_probe`) are computed by a deterministic rule engine over named atoms (aligned to consumer PRODUCT-SPEC §9.3), never by LLM gestalt. Proven transport/visibility infra is copied from `skill-ai-escape-mrc` (package rename `ai_escape_mrc` → `albert`). Dual-mode: cockpit (`albert_input.json` → `albert_challenge.json`) and standalone (proposal → report + email; verdict+light derived).

**Tech Stack:** Python 3, `langgraph`, `langgraph-checkpoint-sqlite`, `claude-agent-sdk`, `tenacity`, `pytest`. StructuredOutput via `ClaudeAgentOptions.output_format={"type":"json_schema","schema":...}`.

**Spec:** `docs/superpowers/specs/2026-06-01-albert-soul-design.md` (v0.3).
**Reference sibling (read-only, to copy infra from):** `D:/D-claude/skills/skill-ai-escape-mrc/`

---

## File Structure

```
skill-cn5-i-am-albert/
  SKILL.md  README.md  requirements.txt  run_albert.py
  albert/
    __init__.py
    no_console.py errors.py utils.py progress.py heartbeat.py stage_summary.py sdk_client.py  (COPY)
    models.py state.py schemas.py signals.py render.py email_delivery.py
    input_adapter.py            # raw proposal | cockpit json -> albert_input shape (synthesizes current_answer)
    cockpit_contract.py         # reference mapping albert_challenge -> cockpit §6.3/§5.2 (R17 proof)
    graph.py
    prompts/
      albert_persona.txt intake_grounding.txt search_reflection.txt ambiguity_hunt.txt
      challenge_generation.txt self_critique_auditor.txt signals_and_gate.txt verdict_render.txt
    phases/
      __init__.py
      phase_0_intake_grounding.py phase_1_ambiguity_hunt.py phase_2_challenge_generation.py
      phase_3_self_critique_audit.py phase_4_signals_and_gate.py phase_5_assemble_render.py
  schemas/ albert_input.schema.json albert_challenge.schema.json
  templates/ albert_report_template.md
  docs/ albert-cockpit-mapping.md  albert-reviews/
  tests/
    test_models_routing.py test_state_shape.py
    test_albert_input_schema.py test_albert_challenge_schema.py
    test_signals_grounding.py            # L4 rule engine
    test_prompts_present.py
    test_input_adapter.py test_phase_0_intake.py test_phase_1_ambiguity.py
    test_phase_2_challenge.py test_phase_3_audit.py test_phase_4_signals.py test_phase_5_assemble.py
    test_render_degraded_guard.py test_cockpit_contract.py test_email_delivery.py
    test_graph_topology.py test_self_critique_loop.py
```

**Phase convention:** a phase is `def phase_x(state: dict) -> dict:` returning the mutated `state`. LLM calls go through `call_claude(model=model_for_role(role), system=load_prompt(name), user=ctx, json_schema=schemas.X, purpose=role)`; multi-round adversarial calls use `ClaudeSession`. Every LLM phase has a deterministic stub fallback and sets `phase_x_status` ∈ `passed`/`failed`.

---

## Task 1: Scaffold + copy infra

**Files:** `albert/__init__.py`, `albert/phases/__init__.py`, `requirements.txt`; copy `no_console.py errors.py utils.py progress.py heartbeat.py stage_summary.py sdk_client.py`.

- [ ] **Step 1: `requirements.txt`**

```
langgraph>=0.2
langgraph-checkpoint-sqlite>=2.0
claude-agent-sdk>=0.1
tenacity>=8
pytest>=8
jsonschema>=4
```

- [ ] **Step 2: Empty package markers** — create `albert/__init__.py` and `albert/phases/__init__.py`.

- [ ] **Step 3: Copy infra and rename package**

```bash
for f in no_console.py errors.py utils.py progress.py heartbeat.py stage_summary.py sdk_client.py; do
  sed -e 's/ai_escape_mrc/albert/g' -e 's/AI Escape MRC/Albert/g' \
    "D:/D-claude/skills/skill-ai-escape-mrc/ai_escape_mrc/$f" > "albert/$f"
done
```

- [ ] **Step 4: Add `DegradedEmissionError` to `albert/errors.py`** (keep `VisibilityContractError`; replace the Phase9*/OutputIdentity classes):

```python
class DegradedEmissionError(Exception):
    """A degraded run (status=='failed') tried to emit a non-refusal verdict/green light."""
    def __init__(self, message: str, predicate: str = "") -> None:
        super().__init__(message)
        self.predicate = predicate
```

- [ ] **Step 5: Verify imports**

Run: `py -3 -c "import albert.sdk_client, albert.progress, albert.heartbeat, albert.utils, albert.errors, albert.stage_summary, albert.no_console"`
Expected: exit 0. (If `stage_summary` imports a trimmed symbol from `errors`, fix that import line.)

- [ ] **Step 6: Commit**

```bash
git add albert/ requirements.txt
git commit -m "feat: scaffold albert package + copy proven infra"
```

---

## Task 2: `albert/models.py`

**Files:** Create `albert/models.py`; Test `tests/test_models_routing.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_models_routing.py
from albert.models import model_for_role, model_label

def test_strong_roles_use_default():
    assert model_for_role("challenge_generation") is None
    assert model_for_role("self_critique_audit") is None
    assert model_for_role("verdict_render") is None

def test_fast_env_routes_non_strong(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODEL", "claude-sonnet-4-6")
    assert model_for_role("ambiguity_hunt") == "claude-sonnet-4-6"
    assert model_for_role("challenge_generation") is None

def test_label():
    assert model_label(None) == "environment-default"
```

- [ ] **Step 2: Run → FAIL** (`No module named 'albert.models'`): `py -3 -m pytest tests/test_models_routing.py -v`

- [ ] **Step 3: Implement**

```python
"""Model routing. Reasoning-heavy roles stay on the strong session default."""
from __future__ import annotations
import os

ENVIRONMENT_DEFAULT_MODEL_LABEL = "environment-default"
_STRONG_ROLES = frozenset({"challenge_generation", "self_critique_audit", "verdict_render"})
_FAST_MODEL_ENV = "ALBERT_FAST_MODEL"


def model_for_role(role: str) -> str | None:
    if role in _STRONG_ROLES:
        return None
    return (os.environ.get(_FAST_MODEL_ENV) or "").strip() or None


def model_label(model: str | None) -> str:
    return model or ENVIRONMENT_DEFAULT_MODEL_LABEL
```

- [ ] **Step 4: Run → PASS**. **Step 5: Commit** `feat: model routing`.

---

## Task 3: `albert/state.py`

**Files:** Create `albert/state.py`; Test `tests/test_state_shape.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_state_shape.py
from albert.state import AlbertState, GENERATORS, CHALLENGE_STATUSES

def test_generators():
    assert GENERATORS == ["winning", "first_principle", "timing",
                          "competitor", "owner_business", "convergence_redteam"]

def test_statuses_are_eight():
    assert len(CHALLENGE_STATUSES) == 8
    assert "needs_albert_decision" in CHALLENGE_STATUSES
    assert "needs_bu_judgment" in CHALLENGE_STATUSES

def test_state_total_false():
    s: AlbertState = {}
    s["current_answer"] = "x"
    assert s["current_answer"] == "x"
```

- [ ] **Step 2: Run → FAIL**: `py -3 -m pytest tests/test_state_shape.py -v`

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
    "needs_bu_judgment", "needs_albert_decision", "needs_source_validation", "blocked",
]


class AlbertState(TypedDict, total=False):
    # Input (the albert_input contract, normalized)
    albert_input: dict
    mode: Literal["cockpit", "standalone"]
    current_answer: str
    original_objective: str
    issue_map: list[dict]
    challenge_map: list[dict]
    evidence: list[dict]
    research_state: dict
    proposal: dict
    run_id: str
    run_dir: str
    user_email: Optional[str]

    # Visibility accumulators (progress wrapper)
    screen_summary: Annotated[Optional[str], _take_last]
    stage_summaries: Annotated[list[dict], operator.add]
    stage_summaries_path: Annotated[Optional[str], _take_last]
    visibility_receipt: Annotated[dict, _take_last]

    # Phase 0
    phase_0_complete: bool
    phase_0_status: Optional[Literal["passed", "failed"]]
    research: list[dict]
    meta_question: dict        # {reframing, higher_level_question, wave2_queries}

    # Phase 1
    phase_1_complete: bool
    phase_1_status: Optional[Literal["passed", "failed"]]
    top_ambiguities: list[dict]

    # Phase 2
    phase_2_complete: bool
    phase_2_status: Optional[Literal["passed", "failed"]]
    albert_challenges: list[dict]
    weak_points: list[dict]
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
    premature_end_risk: dict
    research_drift_risk: dict
    recommended_next_probe: list[dict]
    decision_gate: dict
    reproducible_judgment: str

    # Phase 5
    phase_5_complete: bool
    verdict: Optional[str]
    light: Optional[Literal["green", "yellow", "red"]]
    readiness_score_delta: int
    run_status: Optional[Literal["passed", "failed"]]
    report_path: Optional[str]
    challenge_json_path: Optional[str]
    email_delivery_result: Optional[str]
    email_delivery_error: Optional[str]

    start_time: str
    end_time: Optional[str]
```

- [ ] **Step 4: Run → PASS**. **Step 5: Commit** `feat: AlbertState v0.3`.

---

## Task 4: `albert/schemas.py` + disk contract files

**Files:** Create `albert/schemas.py`, `schemas/albert_input.schema.json`, `schemas/albert_challenge.schema.json`; Test `tests/test_albert_input_schema.py`, `tests/test_albert_challenge_schema.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_albert_challenge_schema.py
import json, jsonschema
from pathlib import Path
from albert import schemas
ROOT = Path(__file__).parent.parent

def test_required_keys():
    props = schemas.ALBERT_CHALLENGE["properties"]
    for k in ("top_ambiguities","albert_challenges","weak_points","missing_business_context",
              "missing_evidence","premature_end_risk","research_drift_risk",
              "recommended_next_probe","readiness_score_delta","run_status"):
        assert k in props

def test_challenge_status_enum_has_eight():
    entry = schemas.ALBERT_CHALLENGE["properties"]["albert_challenges"]["items"]["properties"]
    assert len(entry["status"]["enum"]) == 8

def test_verdict_enum():
    assert schemas.ALBERT_CHALLENGE["properties"]["verdict"]["enum"] == \
        ["可推進","要補證據","方向錯","產品定義不完整"]

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

def test_input_requires_current_answer_and_mode():
    assert set(schemas.ALBERT_INPUT["required"]) >= {"current_answer", "mode"}
    assert schemas.ALBERT_INPUT["properties"]["mode"]["enum"] == ["cockpit", "standalone"]

def test_input_has_research_state():
    assert "research_state" in schemas.ALBERT_INPUT["properties"]

def test_disk_input_matches(tmp_path):
    disk = json.loads((ROOT/"schemas"/"albert_input.schema.json").read_text(encoding="utf-8"))
    assert set(disk["properties"]) == set(schemas.ALBERT_INPUT["properties"])
```

- [ ] **Step 2: Run → FAIL**: `py -3 -m pytest tests/test_albert_challenge_schema.py tests/test_albert_input_schema.py -v`

- [ ] **Step 3: Implement `albert/schemas.py`**

```python
"""StructuredOutput JSON schemas. Top-level type always 'object'."""

GENERATOR_ENUM = ["winning", "first_principle", "timing",
                  "competitor", "owner_business", "convergence_redteam"]
STATUS_ENUM = ["answered", "partially_answered", "needs_external_research", "needs_internal_data",
               "needs_bu_judgment", "needs_albert_decision", "needs_source_validation", "blocked"]
LEVEL_ENUM = ["low", "medium", "high"]

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
    "properties": {
        "top_ambiguities": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "term": {"type": "string"}, "why_dangerous": {"type": "string"},
                "precise_question": {"type": "string"}},
                "required": ["term", "why_dangerous", "precise_question"]},
            "minItems": 3, "maxItems": 3},
    },
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
        "missing_info": {"type": "string"},
        "blocking_owner": {"type": "string"},
        "next_action": {"type": "string"},
        "meeting_ready_response": {"type": "string"},
        "generator": {"type": "string", "enum": GENERATOR_ENUM},
        "bone": {"type": "integer", "minimum": 1, "maximum": 12},
        "high_impact": {"type": "boolean"},
    },
    "required": ["challenge", "why_albert_would_ask", "status", "generator", "bone"],
}

CHALLENGE_GENERATION = {
    "type": "object",
    "properties": {
        "albert_challenges": {"type": "array", "items": _CHALLENGE_ITEM, "minItems": 1},
        "weak_points": {"type": "array", "items": {"type": "object", "properties": {
            "point": {"type": "string"}, "why_it_fails_in_a_meeting": {"type": "string"}},
            "required": ["point"]}},
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
            "classification": {"type": "string", "enum": ["ADDRESSABLE", "RESIDUAL"]},
            "issue": {"type": "string"}, "suggested_sharpening": {"type": "string"}},
            "required": ["classification", "issue"]}},
        "verdict": {"type": "string", "enum": ["CONTINUE", "EXHAUSTED", "REWORK"]},
    },
    "required": ["round", "weaknesses", "verdict"],
}

# Phase 4 LLM produces the ATOMS + the fuzzy judgments; signals.py computes the level.
SIGNALS_AND_GATE = {
    "type": "object",
    "properties": {
        "missing_evidence": {"type": "array", "items": {"type": "object", "properties": {
            "item": {"type": "string"},
            "who_can_answer": {"type": "string", "enum": ["AI", "public", "internal", "customer"]}},
            "required": ["item", "who_can_answer"]}},
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
        "decision_gate": {"type": "object", "properties": {
            "can_decide_now": {"type": "array", "items": {"type": "string"}},
            "cannot_decide": {"type": "array", "items": {"type": "string"}},
            "owners": {"type": "array", "items": {"type": "object", "properties": {
                "area": {"type": "string"}, "owner": {"type": "string"}},
                "required": ["area", "owner"]}}},
            "required": ["can_decide_now", "cannot_decide", "owners"]},
        "reproducible_judgment": {"type": "string"},
    },
    "required": ["premature_end_atoms", "decision_gate"],
}

VERDICT = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
        "readiness_score_delta": {"type": "integer", "minimum": -2, "maximum": 2},
    },
    "required": ["verdict", "light", "readiness_score_delta"],
}

_RISK = {"type": "object", "properties": {
    "level": {"type": "string", "enum": LEVEL_ENUM},
    "atoms": {"type": "object"},
    "grounded_in": {"type": "string", "enum": ["research_state", "inferred"]},
    "why": {"type": "string"},
    "low_confidence": {"type": "boolean"}}, "required": ["level", "grounded_in"]}

ALBERT_CHALLENGE = {
    "type": "object",
    "properties": {
        "audited_answer": {"type": "string"},
        "would_survive_leadership": {"type": "boolean"},
        "top_ambiguities": AMBIGUITY_HUNT["properties"]["top_ambiguities"],
        "albert_challenges": {"type": "array", "items": _CHALLENGE_ITEM},
        "weak_points": CHALLENGE_GENERATION["properties"]["weak_points"],
        "missing_business_context": {"type": "array", "items": {"type": "string"}},
        "missing_evidence": SIGNALS_AND_GATE["properties"]["missing_evidence"],
        "premature_end_risk": _RISK,
        "research_drift_risk": _RISK,
        "recommended_next_probe": SIGNALS_AND_GATE["properties"]["recommended_next_probe"],
        "decision_gate": SIGNALS_AND_GATE["properties"]["decision_gate"],
        "readiness_score_delta": {"type": "integer", "minimum": -2, "maximum": 2},
        "reproducible_judgment": {"type": "string"},
        "run_status": {"type": "string", "enum": ["passed", "failed"]},
        "verdict": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
    },
    "required": ["top_ambiguities", "albert_challenges", "weak_points", "missing_business_context",
                 "missing_evidence", "premature_end_risk", "research_drift_risk",
                 "recommended_next_probe", "readiness_score_delta", "run_status"],
}

ALBERT_INPUT = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["cockpit", "standalone"]},
        "current_answer": {"type": "string"},
        "original_objective": {"type": "string"},
        "issue_map": {"type": "array", "items": {"type": "object"}},
        "challenge_map": {"type": "array", "items": {"type": "object"}},
        "evidence": {"type": "array", "items": {"type": "object"}},
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

- [ ] **Step 5: Run → PASS**: `py -3 -m pytest tests/test_albert_challenge_schema.py tests/test_albert_input_schema.py -v`

- [ ] **Step 6: Commit** `feat: v0.3 StructuredOutput schemas + producer-owned contract files`.

---

## Task 5: `albert/signals.py` — the rule engine (L4 heart)

**Files:** Create `albert/signals.py`; Test `tests/test_signals_grounding.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_signals_grounding.py
from albert.signals import premature_end_level, drift_level, rank_next_probe, grounding_of

_STOP_OK = {"open_high_impact_challenges": 0, "new_info_rate": "low",
            "challenge_map_mostly_classified": True,
            "unresolved_are_human_data_decision_only": True,
            "meta_question_search_found_new_high_impact_angle": False}

def test_all_stop_conditions_met_is_low():
    assert premature_end_level(_STOP_OK) == "low"

def test_open_high_impact_forces_not_low():
    atoms = dict(_STOP_OK, open_high_impact_challenges=2)
    assert premature_end_level(atoms) in ("medium", "high")

def test_two_violations_is_high():
    atoms = dict(_STOP_OK, open_high_impact_challenges=2, new_info_rate="high")
    assert premature_end_level(atoms) == "high"

def test_meta_question_found_blocks_low():
    atoms = dict(_STOP_OK, meta_question_search_found_new_high_impact_angle=True)
    assert premature_end_level(atoms) != "low"

def test_drift_low_when_focus_in_set():
    assert drift_level({"current_focus_in_original_high_value_set": True,
                        "high_value_branch_ignored": False}) == "low"

def test_drift_high_when_ignoring_high_value():
    assert drift_level({"current_focus_in_original_high_value_set": False,
                        "high_value_branch_ignored": True}) == "high"

def test_grounding_inferred_when_no_research_state():
    assert grounding_of({}) == "inferred"
    assert grounding_of({"branches_explored": ["a"]}) == "research_state"

def test_rank_orders_by_impact_then_answerability():
    probes = [{"probe": "a", "impact": "low", "answerability": "high"},
              {"probe": "b", "impact": "high", "answerability": "low"}]
    ranked = rank_next_probe(probes)
    assert ranked[0]["probe"] == "b"           # high impact wins
    assert ranked[0]["priority"] == 1
```

- [ ] **Step 2: Run → FAIL**: `py -3 -m pytest tests/test_signals_grounding.py -v`

- [ ] **Step 3: Implement `albert/signals.py`**

```python
"""Deterministic rule engine for the loop signals (spec §4 / consumer §9.3).

The level of each risk signal is a pure function of named atoms — never an LLM
gestalt. The LLM (phase 4) supplies the atoms; this module computes the level so
it is auditable and cannot be silently downgraded.
"""
from __future__ import annotations

_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0, "unknown": 1}


def grounding_of(research_state: dict | None) -> str:
    """Signals are 'research_state'-grounded only when telemetry was actually given."""
    if research_state and any(research_state.get(k) for k in
                              ("branches_explored", "branches_open", "rounds_so_far",
                               "new_info_rate", "stage_summary")):
        return "research_state"
    return "inferred"


def premature_end_level(atoms: dict) -> str:
    """High premature-end risk = the §9.3 stop conditions are NOT all met.

    §9.3 'safe to stop' conditions (all must hold):
      - new sources mostly repeat        -> new_info_rate in {low, none}
      - no new high-impact meta-question  -> meta_question_search_found_new_high_impact_angle is False
      - no open high-impact challenges    -> open_high_impact_challenges == 0
      - challenge map mostly classified   -> challenge_map_mostly_classified is True
      - unresolved are human/data/decision-> unresolved_are_human_data_decision_only is True
    Count violations: 0 -> low, 1 -> medium, >=2 -> high.
    """
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
    """Deterministic ranking by (impact, answerability) desc; assign 1-based priority."""
    def key(p):
        return (_RANK.get(p.get("impact", "medium"), 2),
                _RANK.get(p.get("answerability", "medium"), 2))
    ranked = sorted(list(probes or []), key=key, reverse=True)
    for i, p in enumerate(ranked, 1):
        p["priority"] = i
    return ranked


def build_risk(level: str, atoms: dict, research_state: dict | None, why: str = "") -> dict:
    grounded = grounding_of(research_state)
    return {"level": level, "atoms": atoms, "grounded_in": grounded,
            "why": why, "low_confidence": grounded == "inferred"}
```

- [ ] **Step 4: Run → PASS**: `py -3 -m pytest tests/test_signals_grounding.py -v`

- [ ] **Step 5: Commit** `feat: rule-structured signal engine (premature_end/drift/next_probe)`.

---

## Task 6: Prompts

**Files:** Create the 8 prompt files; Test `tests/test_prompts_present.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_prompts_present.py
import pytest
from albert.utils import load_prompt
NAMES = ["albert_persona","intake_grounding","search_reflection","ambiguity_hunt",
         "challenge_generation","self_critique_auditor","signals_and_gate","verdict_render"]

@pytest.mark.parametrize("n", NAMES)
def test_loads(n):
    assert len(load_prompt(n)) > 50

def test_persona_has_twelve_bones():
    t = load_prompt("albert_persona")
    for n in range(1, 13):
        assert f"{n}." in t

def test_auditor_adversarial():
    assert "adversarial" in load_prompt("self_critique_auditor").lower()

def test_signals_prompt_demands_atoms_not_level():
    t = load_prompt("signals_and_gate").lower()
    assert "atom" in t and "do not" in t  # instructs the LLM to give atoms, not the final level
```

- [ ] **Step 2: Run → FAIL**: `py -3 -m pytest tests/test_prompts_present.py -v`

- [ ] **Step 3: Write `albert/prompts/albert_persona.txt`** — the 12-bone persona (verbatim from spec §2):

```
You are Albert — a high-standard product & architecture war-room reviewer, a BU-head
mind. You do NOT praise and do NOT summarize. You force DECISION QUALITY: push every
claim until the team can no longer dodge WHY this choice wins and survives a
leadership challenge.

The 12 bones of your interrogation:
1. Force every vague term into a precise definition.
2. Ask "will it win?" of every feature (must-have / nice-to-have / overkill / parity; why we win; backup if customer won't buy).
3. Decompose to first principles (application -> service -> latency/deterministic/safety/availability -> compute placement).
4. Chase local-vs-central compute (command-down vs signal-up; actuator / BLDC controller).
5. Use latency / deterministic numbers to bring fantasy back to reality (latency budget, ADC->compute->PWM, network-latency=0 justification).
6. Reverse-engineer competitor strategy (segment cut; tech/cost/customer/legacy; last-gen benchmark; next-gen roadmap).
7. Force a single owner (no 多頭馬車; who decides; pre-feasibility; binding risk + fallback).
8. Separate internal central thesis from external framing.
9. Converge the war-room NOW (answerable now vs needs customer; the 30-point version now).
10. Ask spec + business + schedule together (cost; cut features for price; feasibility for a commercial offer).
11. Red-team the central thesis (where most likely wrong: market/tech/customer/cost/schedule/ecosystem; who is the contrarian).
12. Chase reproducible judgment, not one-off answers (the reusable checklist this leaves behind).

A question is "soul-grade" only if it (a) targets decision quality not document
completeness, (b) forces a thesis (winning / first-principle / owner / fallback),
(c) is research-backed, not a generic template. Output language: match the input.
```

- [ ] **Step 4: Write the remaining 7 prompts** with these exact contents:

`intake_grounding.txt`:
```
You are Albert preparing to audit a CURRENT ANSWER. Read the current answer and its
domain. Decide what external facts you need to ground a sharp audit: competitor
segment cuts, competitor next-gen roadmap, what a mature SOTA product would do,
public latency/cost benchmarks for this domain. Output a short list of wave-1 search
queries specific to THIS answer's domain (never generic).
```

`search_reflection.txt`:
```
You are Albert reflecting between research waves. Given the current answer and the
wave-1 search results, find the HIGHER-LEVEL meta-question the current answer is NOT
addressing — the question a BU head would raise that reframes the whole problem
("what would a mature SOTA product do?"; "is this benchmarking last gen?"). Output a
reframing, the higher_level_question, and 1-4 wave-2 queries to confirm whether a new
high-impact angle exists. Emit StructuredOutput.
```

`ambiguity_hunt.txt`:
```
You are Albert (bone 1). Read the current answer. List the vague terms that hide a
decision, then select the THREE most DANGEROUS — the ones whose ambiguity would most
likely sink the decision in a leadership meeting. For each: term, why dangerous, the
precise question that forces a definition. Emit StructuredOutput only.
```

`challenge_generation.txt`:
```
You are Albert (bones 2-11) auditing a CURRENT ANSWER, helped by the dangerous
ambiguities, research facts, and the meta-question. Produce albert_challenges: for
each, the challenge, why Albert would ask it, what the current answer says about it
(current_answer), a status from {answered, partially_answered, needs_external_research,
needs_internal_data, needs_bu_judgment, needs_albert_decision, needs_source_validation,
blocked}, confidence, missing_info, blocking_owner, next_action, a meeting_ready_response
candidate, its generator and bone, and high_impact (true/false). Also produce
weak_points (with why_it_fails_in_a_meeting), missing_business_context, and
would_survive_leadership (true/false). Each challenge must be soul-grade and
research-backed. Do NOT pad to a fixed count. Emit StructuredOutput.
```

`self_critique_auditor.txt`:
```
You are an ADVERSARIAL auditor of Albert's own challenges. You do NOT agree easily.
For each challenge decide: sharp, or WEAK. Classify each weakness ADDRESSABLE (too
vague/generic/document-completeness — give the sharpening) or RESIDUAL (only the
customer can resolve). Verdict REWORK if any ADDRESSABLE weakness remains; EXHAUSTED
if every remaining weakness is RESIDUAL. Never rubber-stamp. Emit StructuredOutput.
```

`signals_and_gate.txt`:
```
You are Albert producing the loop signals' INPUT ATOMS and the decision gate. Given
the current answer, the challenges, the research_state telemetry, and the
meta-question search result, output:
- premature_end_atoms: open_high_impact_challenges (count), new_info_rate, whether the
  challenge map is mostly classified, whether unresolved items are human/data/decision
  only, and whether the meta-question search found a new high-impact angle.
- drift_atoms: whether current research focus is in the original objective's high-value
  set, and whether a high-value branch is ignored.
- recommended_next_probe (each with kind meta/object, impact, answerability), missing_evidence
  (who_can_answer), decision_gate (can_decide_now/cannot_decide/owners), reproducible_judgment.
IMPORTANT: report the ATOMS and facts only. Do NOT output the final risk level — the
system computes the level from your atoms. Emit StructuredOutput.
```

`verdict_render.txt`:
```
You are Albert delivering the standalone one-line judgment. Given the ambiguities,
challenges, risks, and decision gate, choose exactly one verdict (可推進 / 要補證據 /
方向錯 / 產品定義不完整), a light (green/yellow/red), and readiness_score_delta in
[-2, 2]. An answer with unresolved dangerous ambiguities, high premature_end_risk, or
customer-only residual evidence cannot be green. Emit StructuredOutput.
```

- [ ] **Step 5: Run → PASS**. **Step 6: Commit** `feat: 12-bone persona + 7 phase prompts`.

---

## Task 7: `albert/input_adapter.py` + Phase 0 (intake + meta-research)

**Files:** Create `albert/input_adapter.py`, `albert/phases/phase_0_intake_grounding.py`; Test `tests/test_input_adapter.py`, `tests/test_phase_0_intake.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_input_adapter.py
from albert.input_adapter import build_input

def test_text_becomes_standalone_with_synth_current_answer():
    inp = build_input(raw_text="Build a zonal controller. No spec yet.", input_json=None)
    assert inp["mode"] == "standalone"
    assert "zonal controller" in inp["current_answer"]
    assert inp["research_state"] == {}

def test_json_passthrough_is_cockpit(tmp_path):
    import json
    p = tmp_path/"in.json"
    p.write_text(json.dumps({"current_answer": "x", "mode": "cockpit",
                             "research_state": {"new_info_rate": "low"}}), encoding="utf-8")
    inp = build_input(raw_text=None, input_json=str(p))
    assert inp["mode"] == "cockpit"
    assert inp["research_state"]["new_info_rate"] == "low"
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
    state = {"albert_input": {"current_answer": "zonal controller, no spec",
                              "mode": "standalone", "proposal": {"domain": "auto"},
                              "research_state": {}}}
    out = phase_0_intake_grounding(state)
    assert out["phase_0_complete"] is True
    assert out["current_answer"]
    assert out["meta_question"]["higher_level_question"] == "hq"
    assert isinstance(out["research"], list) and out["research"]
```

- [ ] **Step 2: Run → FAIL**: `py -3 -m pytest tests/test_input_adapter.py tests/test_phase_0_intake.py -v`

- [ ] **Step 3: Implement `albert/input_adapter.py`**

```python
"""Normalize a raw proposal (standalone) or cockpit input JSON into albert_input."""
import json
from pathlib import Path


def build_input(raw_text: str | None, input_json: str | None) -> dict:
    if input_json:
        data = json.loads(Path(input_json).read_text(encoding="utf-8"))
        data.setdefault("mode", "cockpit")
        data.setdefault("current_answer", "")
        data.setdefault("research_state", {})
        data.setdefault("proposal", {})
        return data
    body = raw_text or ""
    p = Path(body)
    if len(body) < 400 and p.exists() and p.is_file():
        body = p.read_text(encoding="utf-8")
    title = body.strip().splitlines()[0][:120] if body.strip() else "(untitled proposal)"
    # The proposal IS an un-challenged current answer.
    return {
        "mode": "standalone",
        "current_answer": body,
        "original_objective": "",
        "issue_map": [], "challenge_map": [], "evidence": [],
        "research_state": {},
        "proposal": {"title": title, "body": body, "domain": ""},
    }
```

- [ ] **Step 4: Implement `albert/phases/phase_0_intake_grounding.py`**

```python
"""Phase 0: parse input + META-research grounding (wave-1 -> reflect -> wave-2).

Meta-research only (find/confirm higher-level questions & SOTA framing). Object-
research (answering the issue branches) is the cockpit's job and is NOT done here.
websearch() never raises; the phase is 'failed' only if the grounding LLM call
falls back."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude, websearch
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas

_QUERIES_SCHEMA = {"type": "object", "properties": {
    "queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4}},
    "required": ["queries"]}


def phase_0_intake_grounding(state: dict) -> dict:
    inp = state["albert_input"]
    state["mode"] = inp.get("mode", "standalone")
    state["current_answer"] = inp.get("current_answer", "")
    state["original_objective"] = inp.get("original_objective", "")
    state["issue_map"] = inp.get("issue_map", [])
    state["challenge_map"] = inp.get("challenge_map", [])
    state["evidence"] = inp.get("evidence", [])
    state["research_state"] = inp.get("research_state", {}) or {}
    state["proposal"] = inp.get("proposal", {})

    ctx = (f"Current answer:\n{state['current_answer'][:6000]}\n\n"
           f"Domain: {state['proposal'].get('domain','')}\n")
    status = "passed"
    research = []
    meta = {}
    try:
        plan = call_claude(model=model_for_role("intake_grounding"),
                           system=load_prompt("intake_grounding"), user=ctx,
                           json_schema=_QUERIES_SCHEMA, purpose="intake_grounding")
        wave1 = [websearch(q) for q in (plan.get("queries") or [])[:4]]
        research.extend(wave1)
        # Reflect -> meta-question -> wave-2 (borrowed from ai-escape SEARCH_REFLECTION).
        refl_ctx = (ctx + "\nWave-1 results:\n" +
                    "\n".join(f"- {r['query']}: {str(r.get('results',''))[:300]}" for r in wave1))
        meta = call_claude(model=model_for_role("intake_grounding"),
                           system=load_prompt("search_reflection"), user=refl_ctx,
                           json_schema=schemas.SEARCH_REFLECTION, purpose="search_reflection")
        research.extend(websearch(q) for q in (meta.get("wave2_queries") or [])[:4])
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_0 grounding failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        status = "failed"

    state["research"] = research
    state["meta_question"] = meta or {}
    state["phase_0_status"] = status
    state["phase_0_complete"] = True
    return state
```

- [ ] **Step 5: Run → PASS**. **Step 6: Commit** `feat: phase 0 intake + meta-research (wave reflection); dual-mode adapter`.

---

## Task 8: Phase 1 — ambiguity hunt

**Files:** Create `albert/phases/phase_1_ambiguity_hunt.py`; Test `tests/test_phase_1_ambiguity.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_phase_1_ambiguity.py
from albert.phases.phase_1_ambiguity_hunt import phase_1_ambiguity_hunt
def _a(t): return {"term": t, "why_dangerous": "w", "precise_question": "p"}

def test_keeps_three(monkeypatch):
    import albert.phases.phase_1_ambiguity_hunt as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"top_ambiguities": [_a("a"), _a("b"), _a("c")]})
    out = phase_1_ambiguity_hunt({"current_answer": "no spec", "research": []})
    assert len(out["top_ambiguities"]) == 3 and out["phase_1_status"] == "passed"

def test_stub_on_failure(monkeypatch):
    import albert.phases.phase_1_ambiguity_hunt as m
    monkeypatch.setattr(m, "call_claude", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = phase_1_ambiguity_hunt({"current_answer": "x", "research": []})
    assert len(out["top_ambiguities"]) == 3 and out["phase_1_status"] == "failed"
```

- [ ] **Step 2: Run → FAIL**. **Step 3: Implement**

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


def _digest(research, n=3):
    return "\n".join(f"- {r.get('query','')}: {str(r.get('results',''))[:300]}"
                     for r in (research or [])[:n])


def phase_1_ambiguity_hunt(state: dict) -> dict:
    ctx = f"Current answer:\n{state.get('current_answer','')[:6000]}\n\nResearch:\n{_digest(state.get('research'))}\n"
    status = "passed"
    try:
        res = call_claude(model=model_for_role("ambiguity_hunt"),
                          system=load_prompt("ambiguity_hunt"), user=ctx,
                          json_schema=schemas.AMBIGUITY_HUNT, purpose="ambiguity_hunt")
        top = res.get("top_ambiguities") or []
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_1 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        top, status = _stub(), "failed"
    if not isinstance(top, list) or len(top) < 3:
        top = (top or []) + _stub()
    state["top_ambiguities"] = top[:3]
    state["phase_1_status"] = status
    state["phase_1_complete"] = True
    return state
```

- [ ] **Step 4: Run → PASS**. **Step 5: Commit** `feat: phase 1 ambiguity hunt`.

---

## Task 9: Phase 2 — challenge generation

**Files:** Create `albert/phases/phase_2_challenge_generation.py`; Test `tests/test_phase_2_challenge.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_phase_2_challenge.py
from albert.phases.phase_2_challenge_generation import phase_2_challenge_generation

def _resp():
    return {"albert_challenges": [
        {"challenge": "why win?", "why_albert_would_ask": "parity", "status": "needs_bu_judgment",
         "generator": "winning", "bone": 2, "high_impact": True}],
        "weak_points": [{"point": "no ROI", "why_it_fails_in_a_meeting": "no number"}],
        "missing_business_context": ["TAM"], "would_survive_leadership": False}

def test_generates(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp())
    out = phase_2_challenge_generation({"current_answer": "x", "research": [],
                                        "top_ambiguities": [], "meta_question": {}})
    assert out["albert_challenges"][0]["status"] == "needs_bu_judgment"
    assert out["would_survive_leadership"] is False
    assert out["phase_2_status"] == "passed"

def test_uses_rework_feedback(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    captured = {}
    def fake(**k):
        captured["user"] = k["user"]; return _resp()
    monkeypatch.setattr(m, "call_claude", fake)
    state = {"current_answer": "x", "research": [], "top_ambiguities": [], "meta_question": {},
             "phase_3_rounds": [{"weaknesses": [{"classification": "ADDRESSABLE",
                "issue": "vague", "suggested_sharpening": "tie to roadmap"}]}]}
    phase_2_challenge_generation(state)
    assert "tie to roadmap" in captured["user"]

def test_stub_on_failure(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = phase_2_challenge_generation({"current_answer": "x", "research": [],
                                        "top_ambiguities": [], "meta_question": {}})
    assert out["phase_2_status"] == "failed" and out["albert_challenges"]
```

- [ ] **Step 2: Run → FAIL**. **Step 3: Implement**

```python
"""Phase 2 (bones 2-11): generate albert_challenges against the current answer.

On a rework loop (phase_3 -> phase_2), the prior round's ADDRESSABLE sharpenings
are fed back so regeneration is informed."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas


def _stub():
    return {"albert_challenges": [{"challenge": "(LLM unavailable — re-run Albert)",
            "why_albert_would_ask": "n/a", "status": "blocked", "generator": "winning", "bone": 2}],
            "weak_points": [], "missing_business_context": [], "would_survive_leadership": False}


def _prior_sharpenings(state):
    rounds = state.get("phase_3_rounds") or []
    if not rounds:
        return ""
    fixes = [w.get("suggested_sharpening", "") for w in rounds[-1].get("weaknesses", [])
             if isinstance(w, dict) and w.get("classification") == "ADDRESSABLE" and w.get("suggested_sharpening")]
    return ("Prior audit said these were too weak — sharpen them:\n" +
            "\n".join(f"- {f}" for f in fixes) + "\n\n") if fixes else ""


def _digest(items, key, n=4):
    return "\n".join(f"- {str(i.get(key, i))[:200]}" for i in (items or [])[:n])


def phase_2_challenge_generation(state: dict) -> dict:
    meta = state.get("meta_question") or {}
    ctx = (f"{_prior_sharpenings(state)}"
           f"Current answer:\n{state.get('current_answer','')[:6000]}\n\n"
           f"Dangerous ambiguities:\n{_digest(state.get('top_ambiguities'), 'term')}\n\n"
           f"Meta-question: {meta.get('higher_level_question','')}\n\n"
           f"Research:\n{_digest(state.get('research'), 'results', 3)}\n")
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
        res, status = _stub(), "failed"
        challenges = res["albert_challenges"]
    state["albert_challenges"] = challenges
    state["weak_points"] = res.get("weak_points") or []
    state["missing_business_context"] = res.get("missing_business_context") or []
    state["would_survive_leadership"] = bool(res.get("would_survive_leadership", False))
    state["phase_2_status"] = status
    state["phase_2_complete"] = True
    return state
```

- [ ] **Step 4: Run → PASS**. **Step 5: Commit** `feat: phase 2 challenge generation (§5.2 shape + weak_points + business context)`.

---

## Task 10: Phase 3 — self-critique audit

**Files:** Create `albert/phases/phase_3_self_critique_audit.py`; Test `tests/test_phase_3_audit.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_phase_3_audit.py
from albert.phases.phase_3_self_critique_audit import phase_3_self_critique_audit

class _Sess:
    def __init__(self, a): self.a = a
    def __enter__(self): return self
    def __exit__(self, *x): return False
    def ask(self, user, purpose="x"):
        if self.a is None: raise RuntimeError("transport")
        return self.a

def _patch(mp, a):
    import albert.phases.phase_3_self_critique_audit as m
    mp.setattr(m, "ClaudeSession", lambda **k: _Sess(a))

def test_rework(monkeypatch):
    _patch(monkeypatch, {"round": 1, "verdict": "REWORK",
        "weaknesses": [{"classification": "ADDRESSABLE", "issue": "vague"}]})
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_verdict"] == "REWORK" and out["phase_3_status"] == "passed"
    assert out["phase_3_attempt_count"] == 1

def test_exhausted(monkeypatch):
    _patch(monkeypatch, {"round": 1, "verdict": "EXHAUSTED",
        "weaknesses": [{"classification": "RESIDUAL", "issue": "ask customer"}]})
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_verdict"] == "EXHAUSTED"

def test_fallback_forces_exhausted(monkeypatch):
    _patch(monkeypatch, None)
    out = phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}]})
    assert out["phase_3_status"] == "failed" and out["phase_3_verdict"] == "EXHAUSTED"
```

- [ ] **Step 2: Run → FAIL**. **Step 3: Implement**

```python
"""Phase 3: adversarial self-critique of Albert's own challenges (audits sharpness
only). A degraded (fallback) audit may never drive a rework (degraded guard)."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import ClaudeSession
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas


def phase_3_self_critique_audit(state: dict) -> dict:
    state.setdefault("phase_3_rounds", [])
    audit = None
    with ClaudeSession(system=load_prompt("self_critique_auditor"),
                       model=model_for_role("self_critique_audit"),
                       schema=schemas.SELF_CRITIQUE_AUDIT, allow_tools=True,
                       max_turns=3, timeout_sec=240) as sess:
        user = ("Audit these challenges; classify weaknesses; give a verdict.\n\n"
                f"{json.dumps(state['albert_challenges'], ensure_ascii=False)[:20000]}\n\n"
                "Use WebSearch if you need to check whether a challenge is research-backed.")
        try:
            audit = sess.ask(user, purpose="self_critique_audit")
        except VisibilityContractError:
            raise
        except Exception as e:
            sys.stderr.write(f"[WARN] phase_3 failed: {type(e).__name__}: {str(e)[:200]}; fallback\n")
            audit = {"round": 1, "weaknesses": [], "verdict": "EXHAUSTED", "_fallback": True}

    if isinstance(audit, list):
        audit = audit[0] if (len(audit) == 1 and isinstance(audit[0], dict)) else \
                {"round": 1, "weaknesses": audit, "verdict": "EXHAUSTED", "_normalized": True}
    if not isinstance(audit, dict):
        audit = {"round": 1, "weaknesses": [], "verdict": "EXHAUSTED", "_fallback": True}
    state["phase_3_rounds"].append(audit)

    is_fallback = bool(audit.get("_fallback"))
    verdict = "REWORK" if (not is_fallback and audit.get("verdict") == "REWORK") else "EXHAUSTED"
    state["phase_3_verdict"] = verdict
    state["phase_3_status"] = "failed" if is_fallback else "passed"
    state["phase_3_attempt_count"] = state.get("phase_3_attempt_count", 0) + 1
    state["phase_3_complete"] = True
    return state
```

- [ ] **Step 4: Run → PASS**. **Step 5: Commit** `feat: phase 3 adversarial self-critique`.

---

## Task 11: Phase 4 — signals & gate (uses the rule engine)

**Files:** Create `albert/phases/phase_4_signals_and_gate.py`; Test `tests/test_phase_4_signals.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_phase_4_signals.py
from albert.phases.phase_4_signals_and_gate import phase_4_signals_and_gate

def _resp():
    return {"premature_end_atoms": {"open_high_impact_challenges": 2, "new_info_rate": "high",
            "challenge_map_mostly_classified": False, "unresolved_are_human_data_decision_only": False,
            "meta_question_search_found_new_high_impact_angle": True},
            "drift_atoms": {"current_focus_in_original_high_value_set": True, "high_value_branch_ignored": False},
            "recommended_next_probe": [{"probe": "p1", "why": "w", "impact": "high", "answerability": "low"}],
            "missing_evidence": [{"item": "roadmap", "who_can_answer": "public"}],
            "decision_gate": {"can_decide_now": [], "cannot_decide": ["price"], "owners": []},
            "reproducible_judgment": "rj"}

def test_level_computed_from_atoms_not_llm(monkeypatch):
    import albert.phases.phase_4_signals_and_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp())
    out = phase_4_signals_and_gate({"current_answer": "x", "albert_challenges": [],
        "research_state": {"new_info_rate": "high"}})
    assert out["premature_end_risk"]["level"] == "high"      # rule over atoms
    assert out["premature_end_risk"]["grounded_in"] == "research_state"
    assert out["research_drift_risk"]["level"] == "low"
    assert out["recommended_next_probe"][0]["priority"] == 1
    assert out["phase_4_status"] == "passed"

def test_inferred_when_no_research_state(monkeypatch):
    import albert.phases.phase_4_signals_and_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: _resp())
    out = phase_4_signals_and_gate({"current_answer": "x", "albert_challenges": [], "research_state": {}})
    assert out["premature_end_risk"]["grounded_in"] == "inferred"
    assert out["premature_end_risk"]["low_confidence"] is True
```

- [ ] **Step 2: Run → FAIL**. **Step 3: Implement**

```python
"""Phase 4 (bones 7,9,12): produce loop-signal ATOMS via LLM, then compute the
risk LEVELS deterministically via albert.signals (never LLM gestalt)."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert.signals import premature_end_level, drift_level, rank_next_probe, build_risk

_STUB = {"premature_end_atoms": {"open_high_impact_challenges": 1, "new_info_rate": "unknown",
         "challenge_map_mostly_classified": False, "unresolved_are_human_data_decision_only": False,
         "meta_question_search_found_new_high_impact_angle": False},
         "drift_atoms": {}, "recommended_next_probe": [], "missing_evidence": [],
         "decision_gate": {"can_decide_now": [], "cannot_decide": ["(LLM unavailable)"], "owners": []},
         "reproducible_judgment": ""}


def phase_4_signals_and_gate(state: dict) -> dict:
    rs = state.get("research_state") or {}
    ctx = (f"Current answer:\n{state.get('current_answer','')[:3000]}\n\n"
           f"Challenges:\n{json.dumps(state.get('albert_challenges', []), ensure_ascii=False)[:10000]}\n\n"
           f"research_state telemetry:\n{json.dumps(rs, ensure_ascii=False)[:3000]}\n")
    status = "passed"
    try:
        res = call_claude(model=model_for_role("signals_and_gate"),
                          system=load_prompt("signals_and_gate"), user=ctx,
                          json_schema=schemas.SIGNALS_AND_GATE, purpose="signals_and_gate")
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_4 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = dict(_STUB), "failed"

    pe_atoms = res.get("premature_end_atoms") or _STUB["premature_end_atoms"]
    dr_atoms = res.get("drift_atoms") or {}
    state["premature_end_risk"] = build_risk(premature_end_level(pe_atoms), pe_atoms, rs)
    state["research_drift_risk"] = build_risk(drift_level(dr_atoms), dr_atoms, rs)
    state["recommended_next_probe"] = rank_next_probe(res.get("recommended_next_probe") or [])
    state["missing_evidence"] = res.get("missing_evidence") or []
    state["decision_gate"] = res.get("decision_gate") or dict(_STUB["decision_gate"])
    state["reproducible_judgment"] = res.get("reproducible_judgment") or ""
    state["phase_4_status"] = status
    state["phase_4_complete"] = True
    return state
```

- [ ] **Step 4: Run → PASS**. **Step 5: Commit** `feat: phase 4 signals & gate (rule engine)`.

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
        enforce_degraded_guard("failed", "green")

def test_allowed_combos():
    enforce_degraded_guard("failed", "red")
    enforce_degraded_guard("passed", "green")

def test_build_challenge_has_all_required():
    c = build_challenge({"top_ambiguities": [], "albert_challenges": [], "weak_points": [],
        "missing_business_context": [], "missing_evidence": [],
        "premature_end_risk": {"level": "low", "grounded_in": "inferred"},
        "research_drift_risk": {"level": "low", "grounded_in": "inferred"},
        "recommended_next_probe": [], "readiness_score_delta": 0, "run_status": "passed"})
    for k in ("top_ambiguities", "albert_challenges", "premature_end_risk", "run_status"):
        assert k in c
```

- [ ] **Step 2: Run → FAIL**. **Step 3: Implement `albert/render.py`**

```python
"""Assemble the albert_challenge contract, the degraded guard, and the markdown report."""
import json
from pathlib import Path
from albert.errors import DegradedEmissionError

_LIGHT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def enforce_degraded_guard(run_status: str, light: str) -> None:
    if run_status == "failed" and light == "green":
        raise DegradedEmissionError("green light on a degraded run is forbidden", "failed_run_green")


def build_challenge(state: dict) -> dict:
    return {
        "audited_answer": state.get("current_answer", ""),
        "would_survive_leadership": bool(state.get("would_survive_leadership", False)),
        "top_ambiguities": state.get("top_ambiguities", []),
        "albert_challenges": state.get("albert_challenges", []),
        "weak_points": state.get("weak_points", []),
        "missing_business_context": state.get("missing_business_context", []),
        "missing_evidence": state.get("missing_evidence", []),
        "premature_end_risk": state.get("premature_end_risk", {"level": "low", "grounded_in": "inferred"}),
        "research_drift_risk": state.get("research_drift_risk", {"level": "low", "grounded_in": "inferred"}),
        "recommended_next_probe": state.get("recommended_next_probe", []),
        "decision_gate": state.get("decision_gate", {"can_decide_now": [], "cannot_decide": [], "owners": []}),
        "readiness_score_delta": int(state.get("readiness_score_delta", 0)),
        "reproducible_judgment": state.get("reproducible_judgment", ""),
        "run_status": state.get("run_status", "failed"),
        "verdict": state.get("verdict", "產品定義不完整"),
        "light": state.get("light", "red"),
    }


def write_challenge_json(state: dict, run_dir: Path) -> str:
    p = Path(run_dir) / "albert_challenge.json"
    p.write_text(json.dumps(build_challenge(state), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def render_report(state: dict) -> str:
    c = build_challenge(state)
    L = [f"# Albert Review — {state.get('proposal', {}).get('title', '(current answer)')}", "",
         f"**Verdict:** {c['verdict']} {_LIGHT.get(c['light'],'')} · readiness_delta {c['readiness_score_delta']} · "
         f"run_status {c['run_status']} · would_survive_leadership={c['would_survive_leadership']}", "",
         f"**premature_end_risk:** {c['premature_end_risk'].get('level')} "
         f"(grounded_in={c['premature_end_risk'].get('grounded_in')}) · "
         f"**drift_risk:** {c['research_drift_risk'].get('level')}", "",
         "## 最危險的 3 個模糊點"]
    L += [f"- **{a.get('term','')}** — {a.get('why_dangerous','')} → {a.get('precise_question','')}"
          for a in c["top_ambiguities"]]
    L += ["", "## 靈魂拷問 (albert_challenges)"]
    for i, q in enumerate(c["albert_challenges"], 1):
        L.append(f"{i}. [{q.get('status','')}/{q.get('generator','')}] {q.get('challenge','')}"
                 f"  ↳ next: {q.get('next_action','')}")
    L += ["", "## Weak points"] + [f"- {w.get('point','')}: {w.get('why_it_fails_in_a_meeting','')}" for w in c["weak_points"]]
    L += ["", "## Recommended next probe"]
    L += [f"{p.get('priority','')}. [{p.get('kind','')}] {p.get('probe','')} — {p.get('why','')}" for p in c["recommended_next_probe"]]
    L += ["", "## 可複用判斷", c["reproducible_judgment"] or "(none)"]
    return "\n".join(L)


def write_report(state: dict, run_dir: Path) -> str:
    p = Path(run_dir) / "albert_review.md"
    p.write_text(render_report(state), encoding="utf-8")
    return str(p)
```

- [ ] **Step 4: Write `templates/albert_report_template.md`** (reference layout for humans):

```markdown
# Albert Review — {title}
**Verdict:** {verdict} {light} · readiness_delta {delta} · would_survive_leadership {survive}
**premature_end_risk:** {pe} · **drift_risk:** {drift}
## 最危險的 3 個模糊點
{ambiguities}
## 靈魂拷問 (albert_challenges)
{challenges}
## Weak points
{weak_points}
## Recommended next probe
{next_probe}
## 可複用判斷
{reproducible_judgment}
```

- [ ] **Step 5: Run → PASS**. **Step 6: Commit** `feat: render + degraded guard`.

---

## Task 13: `albert/cockpit_contract.py` + R17 contract test

**Files:** Create `albert/cockpit_contract.py`, `docs/albert-cockpit-mapping.md`; Test `tests/test_cockpit_contract.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_cockpit_contract.py
from albert.cockpit_contract import to_cockpit
from albert.state import CHALLENGE_STATUSES

def _golden():
    return {"albert_challenges": [
        {"challenge": "why win?", "why_albert_would_ask": "parity", "current_answer": "",
         "status": "needs_bu_judgment", "confidence": "low", "missing_info": "ROI",
         "blocking_owner": "PM", "next_action": "get ROI", "meeting_ready_response": "..."}],
        "weak_points": [{"point": "no ROI"}], "missing_business_context": ["TAM"],
        "missing_evidence": [{"item": "roadmap", "who_can_answer": "public"}],
        "premature_end_risk": {"level": "high"}, "research_drift_risk": {"level": "low"},
        "recommended_next_probe": [{"probe": "p", "why": "w", "priority": 1}],
        "readiness_score_delta": -1}

def test_maps_all_six_three_agent_outputs():
    out = to_cockpit(_golden())
    ata = out["albert_thought_agent_outputs"]
    for k in ("albert_challenges", "weak_points", "missing_business_context", "missing_evidence",
              "questions_albert_would_ask", "premature_end_risk", "research_drift_risk",
              "recommended_next_probe", "readiness_score_delta"):
        assert k in ata

def test_challenge_map_entries_have_status_in_enum():
    out = to_cockpit(_golden())
    for e in out["albert_challenge_map_entries"]:
        assert e["status"] in CHALLENGE_STATUSES
        assert "meeting_ready_response" in e

def test_questions_are_extracted_from_challenges():
    out = to_cockpit(_golden())
    assert out["albert_thought_agent_outputs"]["questions_albert_would_ask"] == ["why win?"]
```

- [ ] **Step 2: Run → FAIL**. **Step 3: Implement `albert/cockpit_contract.py`**

```python
"""Reference mapping: albert_challenge.json -> cockpit PRODUCT-SPEC §6.3 outputs +
§5.2 Albert Challenge Map entries. Proves Albert's output is fit-for-purpose (R17).
The cockpit owns the production adapter; this is the producer-side proof."""
from __future__ import annotations

_CHALLENGE_MAP_FIELDS = ["challenge", "why_albert_would_ask", "current_answer", "status",
                         "confidence", "evidence_refs", "missing_info", "blocking_owner",
                         "next_action", "meeting_ready_response"]


def _entry(ch: dict) -> dict:
    e = {k: ch.get(k, "") for k in _CHALLENGE_MAP_FIELDS}
    e["evidence_refs"] = ch.get("evidence_refs", [])
    return e


def to_cockpit(challenge: dict) -> dict:
    chs = challenge.get("albert_challenges", [])
    return {
        "albert_thought_agent_outputs": {                       # §6.3
            "albert_challenges": chs,
            "weak_points": challenge.get("weak_points", []),
            "missing_business_context": challenge.get("missing_business_context", []),
            "missing_evidence": challenge.get("missing_evidence", []),
            "questions_albert_would_ask": [c.get("challenge", "") for c in chs],
            "premature_end_risk": challenge.get("premature_end_risk", {}).get("level"),
            "research_drift_risk": challenge.get("research_drift_risk", {}).get("level"),
            "recommended_next_probe": challenge.get("recommended_next_probe", []),
            "readiness_score_delta": challenge.get("readiness_score_delta", 0),
        },
        "albert_challenge_map_entries": [_entry(c) for c in chs],   # §5.2
    }
```

- [ ] **Step 4: Write `docs/albert-cockpit-mapping.md`** — the mapping table from spec §6 (Albert field → cockpit §6.3/§5.2 field), with a note that `albert/cockpit_contract.py` is the executable reference and `tests/test_cockpit_contract.py` is the R17 closed-loop anchor.

- [ ] **Step 5: Run → PASS**. **Step 6: Commit** `feat: cockpit_contract reference mapping + R17 contract test + mapping doc`.

---

## Task 14: `albert/email_delivery.py` + Phase 5 assemble & render

**Files:** Create `albert/email_delivery.py`, `albert/phases/phase_5_assemble_render.py`; Test `tests/test_email_delivery.py`, `tests/test_phase_5_assemble.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_email_delivery.py
import albert.email_delivery as ed
def test_sent(monkeypatch, tmp_path):
    p = tmp_path/"r.md"; p.write_text("b", encoding="utf-8")
    monkeypatch.setattr(ed, "_send_via_outlook", lambda to, subject, body, cc: None)
    assert ed.send_email(to="a@b.com", subject="s", body_path=str(p)) == "sent"
def test_skipped_no_recipient(tmp_path):
    p = tmp_path/"r.md"; p.write_text("b", encoding="utf-8")
    assert ed.send_email(to=None, subject="s", body_path=str(p)) == "skipped"
```

```python
# tests/test_phase_5_assemble.py
from albert.phases.phase_5_assemble_render import phase_5_assemble_render

def _state(tmp_path, statuses):
    s = {"run_dir": str(tmp_path), "run_id": "r", "mode": "standalone",
         "proposal": {"title": "T"}, "current_answer": "a", "top_ambiguities": [],
         "albert_challenges": [], "weak_points": [], "missing_business_context": [],
         "missing_evidence": [], "recommended_next_probe": [],
         "premature_end_risk": {"level": "low", "grounded_in": "inferred"},
         "research_drift_risk": {"level": "low", "grounded_in": "inferred"},
         "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
         "reproducible_judgment": "rj"}
    s.update(statuses); return s

def test_passed_emits_json_and_report(tmp_path, monkeypatch):
    import albert.phases.phase_5_assemble_render as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"verdict": "可推進", "light": "green", "readiness_score_delta": 1})
    monkeypatch.setattr(m, "send_email", lambda **k: "skipped")
    out = phase_5_assemble_render(_state(tmp_path, {f"phase_{i}_status": "passed" for i in range(5)}))
    assert out["run_status"] == "passed" and out["light"] == "green"
    assert out["challenge_json_path"] and out["report_path"]

def test_failed_downgrades_green(tmp_path, monkeypatch):
    import albert.phases.phase_5_assemble_render as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"verdict": "可推進", "light": "green", "readiness_score_delta": 2})
    monkeypatch.setattr(m, "send_email", lambda **k: "skipped")
    out = phase_5_assemble_render(_state(tmp_path, {"phase_0_status": "passed", "phase_1_status": "failed",
        "phase_2_status": "passed", "phase_3_status": "passed", "phase_4_status": "passed"}))
    assert out["run_status"] == "failed" and out["light"] != "green"
```

- [ ] **Step 2: Run → FAIL**. **Step 3: Implement `albert/email_delivery.py`** (same as the sibling Outlook pattern):

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
"""Phase 5: run_status, standalone verdict+light (degraded guard), assemble + emit."""
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


def phase_5_assemble_render(state: dict) -> dict:
    run_status = "failed" if any(state.get(k) == "failed" for k in _STATUS_KEYS) else "passed"
    state["run_status"] = run_status

    ctx = (f"Ambiguities: {state.get('top_ambiguities')}\n"
           f"Challenges: {len(state.get('albert_challenges', []))}\n"
           f"premature_end: {state.get('premature_end_risk', {}).get('level')}\n"
           f"missing_evidence: {state.get('missing_evidence')}\n")
    try:
        v = call_claude(model=model_for_role("verdict_render"), system=load_prompt("verdict_render"),
                        user=ctx, json_schema=schemas.VERDICT, purpose="verdict_render")
        verdict, light, delta = v.get("verdict", "要補證據"), v.get("light", "yellow"), int(v.get("readiness_score_delta", 0))
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_5 verdict failed: {type(e).__name__}: {str(e)[:200]}; refuse\n")
        verdict, light, delta, run_status = "產品定義不完整", "red", -2, "failed"
        state["run_status"] = run_status

    try:
        enforce_degraded_guard(run_status, light)
    except DegradedEmissionError:
        light = "red"
        if verdict == "可推進":
            verdict = "要補證據"

    state["verdict"], state["light"], state["readiness_score_delta"] = verdict, light, delta
    run_dir = Path(state["run_dir"])
    state["challenge_json_path"] = write_challenge_json(state, run_dir)
    state["report_path"] = write_report(state, run_dir)

    if state.get("mode") == "standalone" and state.get("user_email"):
        try:
            state["email_delivery_result"] = send_email(
                to=state["user_email"],
                subject=f"[Albert] {verdict} — {state['proposal'].get('title','review')}",
                body_path=state["report_path"])
        except Exception as e:
            state["email_delivery_result"] = "failed"
            state["email_delivery_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    state["phase_5_complete"] = True
    return state
```

- [ ] **Step 5: Run → PASS**. **Step 6: Commit** `feat: phase 5 assemble + render + email; degraded guard`.

---

## Task 15: `albert/graph.py` + topology & exhaustion-loop tests

**Files:** Create `albert/graph.py`; Test `tests/test_graph_topology.py`, `tests/test_self_critique_loop.py`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_graph_topology.py
from albert.graph import build_graph, _route_after_audit, _max_rework

def test_compiles():
    assert build_graph() is not None

def test_rework_under_cap_loops(monkeypatch):
    monkeypatch.delenv("ALBERT_MAX_REWORK", raising=False)
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}) == "phase_2_challenge_generation"

def test_rework_over_cap_proceeds(monkeypatch):
    monkeypatch.setenv("ALBERT_MAX_REWORK", "2")
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 3}) == "phase_4_signals_and_gate"

def test_exhausted_proceeds():
    assert _route_after_audit({"phase_3_verdict": "EXHAUSTED", "phase_3_attempt_count": 1}) == "phase_4_signals_and_gate"

def test_cap_zero(monkeypatch):
    monkeypatch.setenv("ALBERT_MAX_REWORK", "0")
    assert _max_rework() == 0
    assert _route_after_audit({"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}) == "phase_4_signals_and_gate"
```

```python
# tests/test_self_critique_loop.py
import tempfile
from albert.graph import build_graph

def test_loop_terminates(monkeypatch):
    import albert.phases.phase_0_intake_grounding as p0
    import albert.phases.phase_1_ambiguity_hunt as p1
    import albert.phases.phase_2_challenge_generation as p2
    import albert.phases.phase_3_self_critique_audit as p3
    import albert.phases.phase_4_signals_and_gate as p4
    import albert.phases.phase_5_assemble_render as p5
    monkeypatch.setenv("ALBERT_MAX_REWORK", "2")
    monkeypatch.setattr(p0, "call_claude", lambda **k: {"queries": []} if k["purpose"]=="intake_grounding" else {"higher_level_question":"h","wave2_queries":[]})
    monkeypatch.setattr(p0, "websearch", lambda q: {"query": q, "results": ""})
    monkeypatch.setattr(p1, "call_claude", lambda **k: {"top_ambiguities": [{"term":"t","why_dangerous":"w","precise_question":"p"}]*3})
    monkeypatch.setattr(p2, "call_claude", lambda **k: {"albert_challenges":[{"challenge":"x","why_albert_would_ask":"y","status":"blocked","generator":"winning","bone":2}],"weak_points":[],"missing_business_context":[],"would_survive_leadership":False})
    calls = {"n": 0}
    class _S:
        def __init__(self,**k): pass
        def __enter__(self): return self
        def __exit__(self,*a): return False
        def ask(self,user,purpose="x"):
            calls["n"] += 1
            return {"round": calls["n"], "weaknesses": [], "verdict": "REWORK" if calls["n"]<3 else "EXHAUSTED"}
    monkeypatch.setattr(p3, "ClaudeSession", lambda **k: _S())
    monkeypatch.setattr(p4, "call_claude", lambda **k: {"premature_end_atoms":{"open_high_impact_challenges":0,"new_info_rate":"low"},"drift_atoms":{},"recommended_next_probe":[],"missing_evidence":[],"decision_gate":{"can_decide_now":[],"cannot_decide":[],"owners":[]},"reproducible_judgment":"rj"})
    monkeypatch.setattr(p5, "call_claude", lambda **k: {"verdict":"可推進","light":"green","readiness_score_delta":1})
    monkeypatch.setattr(p5, "send_email", lambda **k: "skipped")
    g = build_graph()
    state = {"albert_input": {"current_answer": "a", "mode": "standalone", "proposal": {}, "research_state": {}},
             "run_dir": tempfile.mkdtemp(), "run_id": "r", "mode": "standalone"}
    final = g.invoke(state, config={"configurable": {"thread_id": "t", "recursion_limit": 100}})
    assert final["phase_5_complete"] is True
    assert calls["n"] == 3 and final["phase_3_attempt_count"] == 3
```

- [ ] **Step 2: Run → FAIL**. **Step 3: Implement `albert/graph.py`**

```python
"""LangGraph StateGraph for the Albert Thought Agent FSM.

START -> phase_0 -> phase_1 -> phase_2 -> phase_3
  phase_3 --[REWORK & attempt<=cap]--> phase_2
  phase_3 --[else]--> phase_4 -> phase_5 -> END
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
from albert.phases.phase_4_signals_and_gate import phase_4_signals_and_gate
from albert.phases.phase_5_assemble_render import phase_5_assemble_render


def _max_rework() -> int:
    try:
        return max(0, int(os.environ.get("ALBERT_MAX_REWORK", "2")))
    except (TypeError, ValueError):
        return 2


def _route_after_audit(state: dict) -> str:
    if state.get("phase_3_verdict") == "REWORK" and state.get("phase_3_attempt_count", 0) <= _max_rework():
        return "phase_2_challenge_generation"
    return "phase_4_signals_and_gate"


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
    g.add_node("phase_0_intake_grounding", _wrap("phase_0_intake_grounding", phase_0_intake_grounding))
    g.add_node("phase_1_ambiguity_hunt", _wrap("phase_1_ambiguity_hunt", phase_1_ambiguity_hunt))
    g.add_node("phase_2_challenge_generation", _wrap("phase_2_challenge_generation", phase_2_challenge_generation))
    g.add_node("phase_3_self_critique_audit", _wrap("phase_3_self_critique_audit", phase_3_self_critique_audit))
    g.add_node("phase_4_signals_and_gate", _wrap("phase_4_signals_and_gate", phase_4_signals_and_gate))
    g.add_node("phase_5_assemble_render", _wrap("phase_5_assemble_render", phase_5_assemble_render))
    g.add_edge(START, "phase_0_intake_grounding")
    g.add_edge("phase_0_intake_grounding", "phase_1_ambiguity_hunt")
    g.add_edge("phase_1_ambiguity_hunt", "phase_2_challenge_generation")
    g.add_edge("phase_2_challenge_generation", "phase_3_self_critique_audit")
    g.add_conditional_edges("phase_3_self_critique_audit", _route_after_audit,
        {"phase_2_challenge_generation": "phase_2_challenge_generation",
         "phase_4_signals_and_gate": "phase_4_signals_and_gate"})
    g.add_edge("phase_4_signals_and_gate", "phase_5_assemble_render")
    g.add_edge("phase_5_assemble_render", END)
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run → PASS**. (If `stage_summary` emitter names differ, align imports.) **Step 5: Commit** `feat: FSM graph with exhaustion conditional edge`.

---

## Task 16: `run_albert.py` + SKILL.md + README + symlink + smoke

**Files:** Create `run_albert.py`, `SKILL.md`, `README.md`.

- [ ] **Step 1: Implement `run_albert.py`**

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
    ap.add_argument("proposal", nargs="?", help="Proposal text or file path (standalone)")
    ap.add_argument("--input", dest="input_json", help="albert_input.json (cockpit)")
    ap.add_argument("--json-out", action="store_true", help="Print only the albert_challenge.json path")
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
        sys.stderr.write(f"[Albert] {final.get('verdict')} ({final.get('light')}) "
                         f"premature_end={final.get('premature_end_risk',{}).get('level')} "
                         f"delta={final.get('readiness_score_delta')}\n")
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
description: Use when auditing a product/architecture answer or proposal from a high-standard BU-head war-room perspective — simulating how Albert would challenge a current answer to force decision quality, not summarize. Acts as the cockpit's Albert Thought Agent. Triggers on Albert review, war-room audit, 靈魂拷問, would this survive leadership, winning thesis, decision gate, premature stop risk, research drift, competitor strategy, will-it-win, readiness audit. LangGraph FSM — intake+meta-research, ambiguity hunt, challenge generation, adversarial self-critique exhaustion loop, rule-grounded stop/continue/drift signals.
execution_mode: both
---

# Albert — Albert Thought Agent (LangGraph-driven)

Albert audits a CURRENT ANSWER and asks: would this survive a leadership challenge,
where is it weak, what should be probed next. He does not praise or summarize. Phase
order and the exhaustion loop are enforced by Python, not markdown.

## Invocation

Cockpit (programmatic — prints the challenge JSON path):

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py --input albert_input.json --json-out

Standalone (review a proposal → report + email):

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py "<proposal text or file>" --user-email you@example.com

Flags: `--resume <run_id>`, `--gc`, `--dry-run`. Env: `ALBERT_MAX_REWORK` (default 2), `ALBERT_FAST_MODEL`.

## Output & contract

`albert_challenge.json` (schema `schemas/albert_challenge.schema.json`): top_ambiguities,
albert_challenges (§5.2 entry shape, 8-value status), weak_points, missing_business_context,
missing_evidence, premature_end_risk / research_drift_risk (rule-grounded), recommended_next_probe,
readiness_score_delta. Mapping to the cockpit's §6.3/§5.2 is in `docs/albert-cockpit-mapping.md`;
`albert/cockpit_contract.py` + `tests/test_cockpit_contract.py` prove the seam (R17). Do not change
the schemas without re-running that test and the cockpit's integration test.
```

- [ ] **Step 3: Write `README.md`** — what Albert is (Albert Thought Agent for the CN5 cockpit), the 12 bones (link spec), invocation, the FSM/exhaustion loop, the rule-grounded signals, env vars, and the R17 seam artifacts.

- [ ] **Step 4: Smoke + full suite**

Run: `py -3 run_albert.py --dry-run "test"` → `Would invoke Albert with run_id=run-...`, exit 0
Run: `py -3 -m pytest tests/ -v` → all PASS

- [ ] **Step 5: Symlink for discovery**

```powershell
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\skill-cn5-i-am-albert" -Target "D:\D-claude\skill-cn5-i-am-albert"
```

- [ ] **Step 6: Commit** `feat: run_albert CLI + SKILL.md + README; symlink + green suite`.

---

## Self-Review (completed)

**Spec coverage:**
- §1 unified pipeline / dual mode / producer-owned schemas → Tasks 4, 7 (`build_input` synthesizes current_answer), 16 (`--json-out`).
- §2 12 bones + 6 generators + soul-grade → Task 6 (persona), schema enums (Task 4), Task 9.
- §3 input incl. `research_state` → Tasks 4, 7.
- §4 superset output contract incl. §5.2 entry + 8-value status → Task 4; L4 rule-grounded signals → Task 5 (`signals.py`) + Task 11 (Phase 4 uses it).
- §5 phases 0-5 + conditional edge + job separation → Tasks 7-11, 15; meta vs object research → Task 7 (Phase 0 wave reflection, object-research explicitly not done).
- §6 seam proof → Task 13 (`cockpit_contract.py`, mapping doc, R17 contract test).
- §7 invocation + env → Tasks 16, 2.
- §8 layout → all tasks.
- §9 testing → every task TDD; `test_signals_grounding` (Task 5), `test_cockpit_contract` (Task 13), `test_degraded_guard` (Task 12), topology + self-critique loop (Task 15).
- §10 open decisions → resolved in tasks (copy infra; strong roles; wave-1+reflect+wave-2; new_info_rate cockpit-provided).

**Placeholder scan:** Task 16 Step 3 (README) describes contents — acceptable (prose doc). All code steps contain complete code.

**Type consistency:** `phase_x_status` keys, role names (`challenge_generation`/`self_critique_audit`/`verdict_render` strong; `intake_grounding`/`ambiguity_hunt`/`signals_and_gate`), schema names (`AMBIGUITY_HUNT`/`CHALLENGE_GENERATION`/`SELF_CRITIQUE_AUDIT`/`SIGNALS_AND_GATE`/`VERDICT`/`ALBERT_CHALLENGE`/`ALBERT_INPUT`/`SEARCH_REFLECTION`), `signals.py` functions (`premature_end_level`/`drift_level`/`rank_next_probe`/`build_risk`/`grounding_of`), node names (`phase_2_challenge_generation`/`phase_4_signals_and_gate`), `to_cockpit` keys — all consistent across tasks.
```
