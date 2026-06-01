# Albert Soul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `skill-cn5-i-am-albert` — a LangGraph FSM reviewer skill that forces decision quality on product/architecture proposals, exposing a producer-owned input/output JSON contract that the CN5 cockpit consumes.

**Architecture:** Six-phase LangGraph `StateGraph` with one conditional edge (Phase 3 self-critique → Phase 2 regenerate) implementing an exhaustion loop. Proven transport/visibility infra is copied from the sibling `skill-ai-escape-mrc` (package rename `ai_escape_mrc` → `albert`); Albert-specific state, schemas, prompts, phases, graph, CLI, and render are written fresh. Dual-mode: standalone (proposal text/file → markdown report + email) and cockpit (`albert_input.json` → `albert_challenge.json`).

**Tech Stack:** Python 3, `langgraph`, `langgraph-checkpoint-sqlite`, `claude-agent-sdk`, `tenacity`, `pytest`. StructuredOutput via `ClaudeAgentOptions.output_format={"type":"json_schema","schema":...}`.

**Reference sibling (read-only source to copy infra from):** `D:/D-claude/skills/skill-ai-escape-mrc/`

---

## File Structure

```
skill-cn5-i-am-albert/
  SKILL.md                              # name + description + execution_mode: both
  README.md
  requirements.txt
  run_albert.py                         # CLI: standalone + cockpit + --resume/--gc/--dry-run
  albert/
    __init__.py
    no_console.py        (COPY)         # Windows subprocess patch
    errors.py            (COPY+trim)    # VisibilityContractError + Albert-specific typed errors
    utils.py             (COPY)         # load_prompt/sluggify/safe_read_text
    progress.py          (COPY)         # per-event JSONL + stderr
    heartbeat.py         (COPY)         # daemon progress thread
    stage_summary.py     (COPY+trim)    # phase start/summary/error emitters used by graph wrapper
    models.py            (NEW)          # model_for_role: strong roles = audit/verdict
    sdk_client.py        (COPY)         # call_claude / ClaudeSession / websearch
    state.py             (NEW)          # AlbertState TypedDict
    schemas.py           (NEW)          # StructuredOutput JSON schemas (per-phase + final)
    render.py            (NEW)          # markdown report + albert_challenge.json writer
    email_delivery.py    (NEW/COPY)     # Outlook COM send (sibling pattern)
    graph.py             (NEW)          # StateGraph + conditional edge
    prompts/
      intake_research.txt
      ambiguity_hunt.txt
      soul_interrogation.txt
      self_critique_auditor.txt
      gap_and_gate.txt
      verdict_render.txt
      albert_persona.txt                # the 12-bone soul, prepended to interrogation prompts
    phases/
      __init__.py
      phase_0_intake_research.py
      phase_1_ambiguity_hunt.py
      phase_2_soul_interrogation.py
      phase_3_self_critique_audit.py
      phase_4_gap_and_gate.py
      phase_5_verdict_render.py
  schemas/
    albert_input.schema.json            # producer-owned input contract (cockpit adapts)
    albert_challenge.schema.json        # producer-owned output contract (R17 seam)
  templates/
    albert_report_template.md
  tests/
    test_graph_topology.py
    test_self_critique_loop.py
    test_degraded_guard.py
    test_albert_input_schema.py
    test_albert_challenge_schema.py
    test_phase_0_intake.py
    test_phase_1_ambiguity.py
    test_phase_2_soul.py
    test_phase_3_audit.py
    test_phase_4_gate.py
    test_phase_5_verdict.py
    test_input_adapter.py               # standalone-text → albert_input shape
    test_email_delivery.py
  docs/
    superpowers/specs/2026-06-01-albert-soul-design.md   (exists)
    superpowers/plans/2026-06-01-albert-soul.md          (this file)
    albert-reviews/                     # standalone report output dir
```

**Conventions used in every phase:**
- A phase is `def phase_x(state: dict) -> dict:` returning the mutated `state` dict. The graph wrapper (`_wrap_with_progress`) merges the return into state and emits visibility receipts.
- LLM calls go through `call_claude(model=model_for_role(<role>), system=load_prompt(<name>), user=<ctx>, json_schema=schemas.<SCHEMA>, purpose=<role>)`.
- `load_prompt("x")` reads `albert/prompts/x.txt` (trailing whitespace stripped).
- Every phase that calls the LLM has a deterministic stub fallback and sets `phase_x_status` = `"passed"` (clean) / `"failed"` (fell back), mirroring the sibling degraded-emission guard.

---

## Task 1: Scaffold package + copy proven infra

**Files:**
- Create: `albert/__init__.py` (empty), `albert/phases/__init__.py` (empty)
- Create: `requirements.txt`
- Copy from sibling (then rename imports): `albert/no_console.py`, `albert/errors.py`, `albert/utils.py`, `albert/progress.py`, `albert/heartbeat.py`, `albert/stage_summary.py`, `albert/sdk_client.py`

- [ ] **Step 1: Create `requirements.txt`**

```
langgraph>=0.2
langgraph-checkpoint-sqlite>=2.0
claude-agent-sdk>=0.1
tenacity>=8
pytest>=8
```

- [ ] **Step 2: Create empty package markers**

Create `albert/__init__.py` and `albert/phases/__init__.py` as empty files.

- [ ] **Step 3: Copy infra files and rename package**

Copy each file from `D:/D-claude/skills/skill-ai-escape-mrc/ai_escape_mrc/` to `albert/`, replacing every `ai_escape_mrc` token with `albert` and every `AI Escape MRC` label with `Albert`:

```bash
for f in no_console.py errors.py utils.py progress.py heartbeat.py stage_summary.py sdk_client.py; do
  sed -e 's/ai_escape_mrc/albert/g' -e 's/AI Escape MRC/Albert/g' \
    "D:/D-claude/skills/skill-ai-escape-mrc/ai_escape_mrc/$f" > "albert/$f"
done
```

- [ ] **Step 4: Trim `albert/errors.py` to Albert's needs**

Keep `VisibilityContractError`. Replace the Phase9* / OutputIdentityContractError classes with one Albert-specific error:

```python
class DegradedEmissionError(Exception):
    """A run that fell back (status=='failed') tried to emit a non-refusal verdict.

    Raised by phase_5 when a green/yellow light would be emitted on top of a
    degraded run. Per R13: refuse rather than ship a self-exonerating warning.
    """
    def __init__(self, message: str, predicate: str = "") -> None:
        super().__init__(message)
        self.predicate = predicate
```

- [ ] **Step 5: Verify infra imports cleanly**

Run: `py -3 -c "import albert.sdk_client, albert.progress, albert.heartbeat, albert.utils, albert.errors, albert.stage_summary, albert.no_console"`
Expected: no output, exit 0. (If `stage_summary` references symbols that were trimmed from `errors`, fix the import line in `stage_summary.py` to match.)

- [ ] **Step 6: Commit**

```bash
git add albert/ requirements.txt
git commit -m "feat: scaffold albert package + copy proven transport/visibility infra"
```

---

## Task 2: `albert/models.py` — model routing

**Files:**
- Create: `albert/models.py`
- Test: `tests/test_models_routing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_routing.py
import os
from albert.models import model_for_role, model_label

def test_strong_roles_use_session_default():
    assert model_for_role("self_critique_audit") is None
    assert model_for_role("verdict_render") is None

def test_non_strong_role_default_is_none(monkeypatch):
    monkeypatch.delenv("ALBERT_FAST_MODEL", raising=False)
    assert model_for_role("ambiguity_hunt") is None

def test_fast_model_env_routes_non_strong(monkeypatch):
    monkeypatch.setenv("ALBERT_FAST_MODEL", "claude-sonnet-4-6")
    assert model_for_role("ambiguity_hunt") == "claude-sonnet-4-6"
    assert model_for_role("self_critique_audit") is None  # strong role ignores fast override

def test_model_label():
    assert model_label(None) == "environment-default"
    assert model_label("claude-opus-4-8") == "claude-opus-4-8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_models_routing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'albert.models'`

- [ ] **Step 3: Write `albert/models.py`**

```python
"""Model routing for Albert SDK calls.

Default: do not set ClaudeAgentOptions.model so the SDK uses the user's active
session model. The reasoning-heavy roles (self-critique audit, verdict) stay on
the strong session default even when a fast model is opted in for the rest.
"""
from __future__ import annotations
import os

ENVIRONMENT_DEFAULT_MODEL_LABEL = "environment-default"

_STRONG_ROLES = frozenset({
    "soul_interrogation",
    "self_critique_audit",
    "verdict_render",
})
_FAST_MODEL_ENV = "ALBERT_FAST_MODEL"


def model_for_role(role: str) -> str | None:
    if role in _STRONG_ROLES:
        return None
    fast = (os.environ.get(_FAST_MODEL_ENV) or "").strip()
    return fast or None


def model_label(model: str | None) -> str:
    return model or ENVIRONMENT_DEFAULT_MODEL_LABEL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_models_routing.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add albert/models.py tests/test_models_routing.py
git commit -m "feat: model_for_role with strong reasoning roles"
```

---

## Task 3: `albert/state.py` — FSM state

**Files:**
- Create: `albert/state.py`
- Test: `tests/test_state_shape.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state_shape.py
from albert.state import AlbertState, GENERATORS

def test_generators_are_six():
    assert GENERATORS == [
        "winning", "first_principle", "timing",
        "competitor", "owner_business", "convergence_redteam",
    ]

def test_state_is_typeddict_total_false():
    # total=False => instantiable empty without KeyError at type level
    s: AlbertState = {}
    s["proposal"] = {"title": "t", "body": "b", "domain": "d"}
    assert s["proposal"]["title"] == "t"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_state_shape.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'albert.state'`

- [ ] **Step 3: Write `albert/state.py`**

```python
"""AlbertState: LangGraph state schema for the Albert reviewer FSM."""
import operator
from typing import Annotated, TypedDict, Literal, Optional


def _take_last(_a, b):
    return b


GENERATORS = [
    "winning", "first_principle", "timing",
    "competitor", "owner_business", "convergence_redteam",
]


class AlbertState(TypedDict, total=False):
    # Input
    proposal: dict            # {title, body, domain}
    albert_input: dict        # full parsed input contract (cockpit) or synthesized (standalone)
    mode: Literal["standalone", "cockpit"]
    run_id: str
    run_dir: str
    user_email: Optional[str]
    operator_email: Optional[str]

    # Visibility accumulators (written by every node's progress wrapper)
    screen_summary: Annotated[Optional[str], _take_last]
    stage_summaries: Annotated[list[dict], operator.add]
    stage_summaries_path: Annotated[Optional[str], _take_last]
    visibility_receipt: Annotated[dict, _take_last]

    # Phase 0: intake + research
    phase_0_complete: bool
    phase_0_status: Optional[Literal["passed", "failed"]]
    research: list[dict]          # websearch results grounding the interrogation

    # Phase 1: ambiguity hunt
    phase_1_complete: bool
    phase_1_status: Optional[Literal["passed", "failed"]]
    top_ambiguities: list[dict]   # exactly 3 {term, why_dangerous, precise_question}

    # Phase 2: soul interrogation
    phase_2_complete: bool
    phase_2_status: Optional[Literal["passed", "failed"]]
    soul_questions: list[dict]    # variable length {q, generator, bone, grounding}

    # Phase 3: self-critique audit (exhaustion loop with phase 2)
    phase_3_complete: bool
    phase_3_status: Optional[Literal["passed", "failed"]]
    phase_3_rounds: list[dict]
    phase_3_verdict: Optional[Literal["EXHAUSTED", "REWORK"]]
    phase_3_attempt_count: int

    # Phase 4: evidence gap + decision gate
    phase_4_complete: bool
    phase_4_status: Optional[Literal["passed", "failed"]]
    evidence_gaps: list[dict]     # {item, who_can_answer, needed_before}
    decision_gate: dict           # {can_decide_now, cannot_decide, owners}
    reproducible_judgment: str

    # Phase 5: verdict + render + emit
    phase_5_complete: bool
    verdict: Optional[str]        # 可推進 / 要補證據 / 方向錯 / 產品定義不完整
    light: Optional[Literal["green", "yellow", "red"]]
    readiness_delta: int
    run_status: Optional[Literal["passed", "failed"]]
    report_path: Optional[str]
    challenge_json_path: Optional[str]
    email_delivery_result: Optional[str]
    email_delivery_error: Optional[str]

    # Metadata
    start_time: str
    end_time: Optional[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_state_shape.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add albert/state.py tests/test_state_shape.py
git commit -m "feat: AlbertState FSM state schema"
```

---

## Task 4: `albert/schemas.py` + JSON contract files

**Files:**
- Create: `albert/schemas.py`
- Create: `schemas/albert_input.schema.json`, `schemas/albert_challenge.schema.json`
- Test: `tests/test_albert_challenge_schema.py`, `tests/test_albert_input_schema.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_albert_challenge_schema.py
import json, jsonschema  # jsonschema ships transitively; if absent, validate structurally
from pathlib import Path
from albert import schemas

ROOT = Path(__file__).parent.parent

def _valid_challenge():
    return {
        "top_ambiguities": [
            {"term": "no spec", "why_dangerous": "hides which spec is missing",
             "precise_question": "high-level / impl / customer / winning spec?"}
        ] * 3,
        "soul_questions": [
            {"q": "why do we win?", "generator": "winning", "bone": 2, "grounding": "internal"}
        ],
        "evidence_gaps": [
            {"item": "competitor roadmap", "who_can_answer": "public", "needed_before": "feasibility"}
        ],
        "decision_gate": {"can_decide_now": ["scope"], "cannot_decide": ["price"],
                          "owners": [{"area": "latency", "owner": "TBD"}]},
        "verdict": "要補證據",
        "light": "yellow",
        "readiness_delta": -1,
        "reproducible_judgment": "checklist X",
        "run_status": "passed",
    }

def test_final_schema_required_keys_present():
    props = schemas.ALBERT_CHALLENGE["properties"]
    for key in ("top_ambiguities", "soul_questions", "evidence_gaps",
                "decision_gate", "verdict", "light", "readiness_delta",
                "reproducible_judgment", "run_status"):
        assert key in props

def test_verdict_and_light_are_enums():
    assert schemas.ALBERT_CHALLENGE["properties"]["verdict"]["enum"] == \
        ["可推進", "要補證據", "方向錯", "產品定義不完整"]
    assert schemas.ALBERT_CHALLENGE["properties"]["light"]["enum"] == \
        ["green", "yellow", "red"]

def test_top_ambiguities_exactly_three():
    amb = schemas.ALBERT_CHALLENGE["properties"]["top_ambiguities"]
    assert amb["minItems"] == 3 and amb["maxItems"] == 3

def test_disk_schema_matches_module():
    disk = json.loads((ROOT / "schemas" / "albert_challenge.schema.json").read_text(encoding="utf-8"))
    assert disk["properties"]["verdict"]["enum"] == \
        schemas.ALBERT_CHALLENGE["properties"]["verdict"]["enum"]

def test_sample_challenge_conforms():
    jsonschema.validate(_valid_challenge(), schemas.ALBERT_CHALLENGE)
```

```python
# tests/test_albert_input_schema.py
import json
from pathlib import Path
from albert import schemas
ROOT = Path(__file__).parent.parent

def test_input_schema_has_proposal_and_mode():
    props = schemas.ALBERT_INPUT["properties"]
    assert "proposal" in props and "mode" in props
    assert props["mode"]["enum"] == ["standalone", "cockpit"]

def test_disk_input_schema_matches_module():
    disk = json.loads((ROOT / "schemas" / "albert_input.schema.json").read_text(encoding="utf-8"))
    assert set(disk["properties"]) == set(schemas.ALBERT_INPUT["properties"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m pytest tests/test_albert_challenge_schema.py tests/test_albert_input_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'albert.schemas'`

- [ ] **Step 3: Write `albert/schemas.py`**

```python
"""StructuredOutput JSON schemas for Albert phases.

Passed to call_claude(json_schema=...) → SDK constrained decoding. Top-level
type is always 'object' (Anthropic requirement).
"""

GENERATOR_ENUM = ["winning", "first_principle", "timing",
                  "competitor", "owner_business", "convergence_redteam"]

AMBIGUITY_HUNT = {
    "type": "object",
    "properties": {
        "all_vague_terms": {"type": "array", "items": {"type": "string"}},
        "top_ambiguities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "why_dangerous": {"type": "string"},
                    "precise_question": {"type": "string"},
                },
                "required": ["term", "why_dangerous", "precise_question"],
            },
            "minItems": 3, "maxItems": 3,
        },
    },
    "required": ["top_ambiguities"],
}

SOUL_INTERROGATION = {
    "type": "object",
    "properties": {
        "soul_questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "generator": {"type": "string", "enum": GENERATOR_ENUM},
                    "bone": {"type": "integer", "minimum": 1, "maximum": 12},
                    "grounding": {"type": "string"},
                },
                "required": ["q", "generator", "bone"],
            },
            "minItems": 1,
        },
    },
    "required": ["soul_questions"],
}

SELF_CRITIQUE_AUDIT = {
    "type": "object",
    "properties": {
        "round": {"type": "integer"},
        "weaknesses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_index": {"type": ["integer", "null"]},
                    "classification": {"type": "string", "enum": ["ADDRESSABLE", "RESIDUAL"]},
                    "issue": {"type": "string"},
                    "suggested_sharpening": {"type": "string"},
                },
                "required": ["classification", "issue"],
            },
        },
        "verdict": {"type": "string", "enum": ["CONTINUE", "EXHAUSTED", "REWORK"]},
    },
    "required": ["round", "weaknesses", "verdict"],
}

GAP_AND_GATE = {
    "type": "object",
    "properties": {
        "evidence_gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "who_can_answer": {"type": "string", "enum": ["AI", "public", "internal", "customer"]},
                    "needed_before": {"type": "string"},
                },
                "required": ["item", "who_can_answer"],
            },
        },
        "decision_gate": {
            "type": "object",
            "properties": {
                "can_decide_now": {"type": "array", "items": {"type": "string"}},
                "cannot_decide": {"type": "array", "items": {"type": "string"}},
                "owners": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"area": {"type": "string"}, "owner": {"type": "string"}},
                        "required": ["area", "owner"],
                    },
                },
            },
            "required": ["can_decide_now", "cannot_decide", "owners"],
        },
        "reproducible_judgment": {"type": "string"},
    },
    "required": ["evidence_gaps", "decision_gate"],
}

VERDICT = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
        "readiness_delta": {"type": "integer", "minimum": -2, "maximum": 2},
        "one_line": {"type": "string"},
    },
    "required": ["verdict", "light", "readiness_delta"],
}

# Final assembled contract (validated on disk + emitted to cockpit).
ALBERT_CHALLENGE = {
    "type": "object",
    "properties": {
        "top_ambiguities": AMBIGUITY_HUNT["properties"]["top_ambiguities"],
        "soul_questions": SOUL_INTERROGATION["properties"]["soul_questions"],
        "evidence_gaps": GAP_AND_GATE["properties"]["evidence_gaps"],
        "decision_gate": GAP_AND_GATE["properties"]["decision_gate"],
        "verdict": VERDICT["properties"]["verdict"],
        "light": VERDICT["properties"]["light"],
        "readiness_delta": VERDICT["properties"]["readiness_delta"],
        "reproducible_judgment": {"type": "string"},
        "run_status": {"type": "string", "enum": ["passed", "failed"]},
    },
    "required": ["top_ambiguities", "soul_questions", "evidence_gaps",
                 "decision_gate", "verdict", "light", "readiness_delta", "run_status"],
}

ALBERT_INPUT = {
    "type": "object",
    "properties": {
        "proposal": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "body": {"type": "string"},
                           "domain": {"type": "string"}},
            "required": ["body"],
        },
        "issue_map": {"type": "array", "items": {"type": "object"}},
        "challenge_map": {"type": "array", "items": {"type": "object"}},
        "evidence": {"type": "array", "items": {"type": "object"}},
        "draft_answer": {"type": "string"},
        "readiness": {"type": "integer"},
        "mode": {"type": "string", "enum": ["standalone", "cockpit"]},
    },
    "required": ["proposal", "mode"],
}
```

- [ ] **Step 4: Write the two disk schema files**

`schemas/albert_challenge.schema.json` and `schemas/albert_input.schema.json` are the JSON dumps of `ALBERT_CHALLENGE` and `ALBERT_INPUT` with a `$schema` + `title` header. Generate them deterministically from the module so they never drift:

```bash
py -3 -c "import json; from albert import schemas; \
open('schemas/albert_challenge.schema.json','w',encoding='utf-8').write(json.dumps({'\$schema':'https://json-schema.org/draft/2020-12/schema','title':'AlbertChallenge', **schemas.ALBERT_CHALLENGE}, ensure_ascii=False, indent=2)); \
open('schemas/albert_input.schema.json','w',encoding='utf-8').write(json.dumps({'\$schema':'https://json-schema.org/draft/2020-12/schema','title':'AlbertInput', **schemas.ALBERT_INPUT}, ensure_ascii=False, indent=2))"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3 -m pytest tests/test_albert_challenge_schema.py tests/test_albert_input_schema.py -v`
Expected: PASS. (If `jsonschema` is not importable, replace the `jsonschema.validate` call in `test_sample_challenge_conforms` with a structural assertion on required keys.)

- [ ] **Step 6: Commit**

```bash
git add albert/schemas.py schemas/ tests/test_albert_challenge_schema.py tests/test_albert_input_schema.py
git commit -m "feat: Albert StructuredOutput schemas + producer-owned contract files"
```

---

## Task 5: Prompts — the 12-bone soul + per-phase system prompts

**Files:**
- Create: `albert/prompts/albert_persona.txt`, `intake_research.txt`, `ambiguity_hunt.txt`, `soul_interrogation.txt`, `self_critique_auditor.txt`, `gap_and_gate.txt`, `verdict_render.txt`
- Test: `tests/test_prompts_present.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompts_present.py
import pytest
from albert.utils import load_prompt

NAMES = ["albert_persona", "intake_research", "ambiguity_hunt",
         "soul_interrogation", "self_critique_auditor", "gap_and_gate", "verdict_render"]

@pytest.mark.parametrize("name", NAMES)
def test_prompt_loads_and_nonempty(name):
    text = load_prompt(name)
    assert len(text) > 50

def test_persona_lists_twelve_bones():
    text = load_prompt("albert_persona")
    for n in range(1, 13):
        assert f"{n}." in text

def test_auditor_is_adversarial():
    text = load_prompt("self_critique_auditor").lower()
    assert "adversarial" in text or "do not agree" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_prompts_present.py -v`
Expected: FAIL — `FileNotFoundError` for `albert_persona.txt`

- [ ] **Step 3: Write `albert/prompts/albert_persona.txt`**

```
You are Albert — a high-standard product & architecture war-room reviewer.
Your job is NOT to praise and NOT to summarize a meeting. Your job is to force
DECISION QUALITY: push every claim until the team can no longer dodge WHY this
choice wins.

The 12 bones of your interrogation:
1. Force every vague term into a precise definition ("no spec" = no high-level / implementation / customer-requirement / winning spec?).
2. Ask "will it win?" of every feature (must-have / nice-to-have / overkill / competitor-parity; why we win; backup if customer won't buy).
3. Decompose the product to first principles (application -> service -> latency/deterministic/safety/availability -> compute placement).
4. Chase local-vs-central compute until it can't be dodged (command-down vs signal-up; actuator / BLDC controller).
5. Use latency / deterministic numbers to bring fantasy back to reality (latency budget, ADC->compute->PWM path, network-latency=0 justification).
6. Reverse-engineer competitor strategy (segment cut; tech/cost/customer/legacy; are we benchmarking last gen; next-gen roadmap).
7. Force a single owner (no 多頭馬車; who decides; what must be answered pre-feasibility; binding risk + fallback).
8. Separate internal central thesis from external framing (discovery/alignment/commitment/negotiation; what to tell vs only listen).
9. Converge the war-room NOW (answerable by AI/public/internal know-how now vs truly needs the customer; the 30-point version now).
10. Ask spec + business + schedule together (cost impact; cut features for lowest price; feasibility ready for a commercial offer).
11. Red-team the central thesis (where it is most likely wrong: market/tech/customer/cost/schedule/ecosystem; who is the contrarian).
12. Chase reproducible judgment, not one-off answers (what reusable judgment / checklist this review leaves behind).

A question is "soul-grade" only if it (a) targets decision quality not document
completeness, (b) forces a thesis (winning / first-principle / owner / fallback),
and (c) is research-backed, not a generic template anyone could ask.

Output language: match the proposal's language (CN/EN mix is fine).
```

- [ ] **Step 4: Write the per-phase prompts**

Each begins by referencing the persona role, then states the task and demands StructuredOutput. Exact contents:

`intake_research.txt`:
```
You are Albert preparing to interrogate a proposal. First understand the
proposal, then identify what external facts you need to ground a sharp review:
competitor segment cuts, competitor next-gen roadmap, public latency/cost
benchmarks for this domain. Produce a concise list of search queries and, given
the provided search results, the 3-6 facts most useful for an un-dodgeable
interrogation. Be specific to THIS proposal's domain, never generic.
```

`ambiguity_hunt.txt`:
```
You are Albert (bone 1). Read the proposal. List every vague term that hides a
decision ("no spec", "uncertain", "high performance", "low latency", "the
customer wants"). Then select the THREE most DANGEROUS — the ones whose
ambiguity, if left unresolved, would most likely sink the decision. For each:
the term, why it is dangerous, and the precise question that forces a definition.
Emit StructuredOutput only.
```

`soul_interrogation.txt`:
```
You are Albert (bones 2-11). Using the proposal, the 3 dangerous ambiguities,
and the research facts, generate soul questions across these six generators:
winning, first_principle, timing, competitor, owner_business, convergence_redteam.
Each question must be soul-grade (decision quality, forces a thesis, research-
backed). Tag each with its generator and the bone number it comes from. Do NOT
pad to a fixed count — ask exactly as many as the proposal's weaknesses demand.
Ground competitor/timing questions in the research facts. Emit StructuredOutput.
```

`self_critique_auditor.txt`:
```
You are an ADVERSARIAL auditor of Albert's own questions. You do NOT agree
easily. For each soul question, decide: is it sharp (decision-quality, forces a
thesis, research-backed) or is it WEAK? Classify each weakness:
- ADDRESSABLE: the question is too vague/generic/document-completeness and CAN
  be sharpened now — give the sharpening.
- RESIDUAL: the gap is inherent (only the customer can resolve) — log it.
Verdict:
- REWORK if any ADDRESSABLE weakness remains (the questions must be regenerated).
- EXHAUSTED if every remaining weakness is RESIDUAL (nothing left to sharpen).
Never rubber-stamp; a passing score hides weakness. Emit StructuredOutput.
```

`gap_and_gate.txt`:
```
You are Albert (bones 7, 9, 12). Given the proposal and the soul questions,
produce: (1) evidence_gaps — for each open question, what evidence is needed and
who_can_answer it: AI / public / internal (answerable now) vs customer (residual
until asked). (2) decision_gate — can_decide_now, cannot_decide, and the single
owner per area (no 多頭馬車). (3) reproducible_judgment — the reusable checklist
this review leaves behind. Emit StructuredOutput.
```

`verdict_render.txt`:
```
You are Albert delivering the one-line judgment. Given the ambiguities, soul
questions, evidence gaps, and decision gate, choose exactly one verdict:
可推進 / 要補證據 / 方向錯 / 產品定義不完整, a traffic light (green/yellow/red),
and a readiness_delta in [-2, 2] reflecting how much this review should move the
proposal's readiness. A proposal with unresolved dangerous ambiguities or
customer-only residual evidence cannot be green. Emit StructuredOutput.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_prompts_present.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add albert/prompts/ tests/test_prompts_present.py
git commit -m "feat: 12-bone persona + per-phase system prompts"
```

---

## Task 6: Phase 0 — intake + research

**Files:**
- Create: `albert/phases/phase_0_intake_research.py`
- Create: `albert/input_adapter.py` (standalone-text → albert_input shape)
- Test: `tests/test_phase_0_intake.py`, `tests/test_input_adapter.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_input_adapter.py
from albert.input_adapter import build_input

def test_text_becomes_standalone_input():
    inp = build_input(raw_text="We will build a zonal controller. No spec yet.", input_json=None)
    assert inp["mode"] == "standalone"
    assert "zonal controller" in inp["proposal"]["body"]

def test_json_passthrough_is_cockpit(tmp_path):
    import json
    p = tmp_path / "in.json"
    p.write_text(json.dumps({"proposal": {"body": "x"}, "mode": "cockpit"}), encoding="utf-8")
    inp = build_input(raw_text=None, input_json=str(p))
    assert inp["mode"] == "cockpit"
    assert inp["proposal"]["body"] == "x"
```

```python
# tests/test_phase_0_intake.py
from albert.phases.phase_0_intake_research import phase_0_intake_research

def test_phase_0_populates_proposal_and_marks_complete(monkeypatch):
    import albert.phases.phase_0_intake_research as m
    monkeypatch.setattr(m, "websearch", lambda q: {"query": q, "results": "competitor X moved compute to zone"})
    monkeypatch.setattr(m, "call_claude", lambda **k: {"queries": ["q1"], "facts": ["fact1"]})
    state = {"albert_input": {"proposal": {"body": "zonal controller, no spec"}, "mode": "standalone"}}
    out = phase_0_intake_research(state)
    assert out["phase_0_complete"] is True
    assert out["phase_0_status"] in ("passed", "failed")
    assert out["proposal"]["body"]
    assert isinstance(out["research"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m pytest tests/test_input_adapter.py tests/test_phase_0_intake.py -v`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write `albert/input_adapter.py`**

```python
"""Normalize either a raw proposal (standalone) or a cockpit input JSON into the
albert_input contract shape."""
import json
from pathlib import Path


def build_input(raw_text: str | None, input_json: str | None) -> dict:
    if input_json:
        data = json.loads(Path(input_json).read_text(encoding="utf-8"))
        data.setdefault("mode", "cockpit")
        data.setdefault("proposal", {})
        data["proposal"].setdefault("body", "")
        return data
    # Standalone: raw text may be a file path or literal text.
    body = raw_text or ""
    p = Path(body)
    if len(body) < 400 and p.exists() and p.is_file():
        body = p.read_text(encoding="utf-8")
    title = body.strip().splitlines()[0][:120] if body.strip() else "(untitled proposal)"
    return {
        "proposal": {"title": title, "body": body, "domain": ""},
        "issue_map": [], "challenge_map": [], "evidence": [],
        "draft_answer": "", "readiness": 0, "mode": "standalone",
    }
```

- [ ] **Step 4: Write `albert/phases/phase_0_intake_research.py`**

```python
"""Phase 0: parse input + gather grounding research.

Research is OPTIONAL augmentation: websearch() never raises (it degrades to an
error-tagged result). The phase is 'failed' only if the LLM planning call falls
back to a stub."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude, websearch
from albert.models import model_for_role
from albert.utils import load_prompt

_RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
        "facts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["queries"],
}


def phase_0_intake_research(state: dict) -> dict:
    inp = state["albert_input"]
    proposal = inp["proposal"]
    state["proposal"] = proposal
    state["mode"] = inp.get("mode", "standalone")

    context = (
        f"Proposal title: {proposal.get('title','')}\n"
        f"Domain: {proposal.get('domain','')}\n\n"
        f"Proposal body:\n{proposal.get('body','')[:6000]}\n"
    )
    status = "passed"
    try:
        plan = call_claude(
            model=model_for_role("intake_research"),
            system=load_prompt("intake_research"),
            user=context,
            json_schema=_RESEARCH_SCHEMA,
            purpose="intake_research",
        )
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_0 research planning failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        plan = {"queries": [], "facts": []}
        status = "failed"

    research = []
    for q in (plan.get("queries") or [])[:5]:
        research.append(websearch(q))
    # Carry the LLM-proposed facts alongside raw search hits.
    if plan.get("facts"):
        research.append({"query": "_planned_facts", "results": "\n".join(plan["facts"])})

    state["research"] = research
    state["phase_0_status"] = status
    state["phase_0_complete"] = True
    return state
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3 -m pytest tests/test_input_adapter.py tests/test_phase_0_intake.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add albert/phases/phase_0_intake_research.py albert/input_adapter.py tests/test_input_adapter.py tests/test_phase_0_intake.py
git commit -m "feat: phase 0 intake + grounding research, dual-mode input adapter"
```

---

## Task 7: Phase 1 — ambiguity hunt

**Files:**
- Create: `albert/phases/phase_1_ambiguity_hunt.py`
- Test: `tests/test_phase_1_ambiguity.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase_1_ambiguity.py
from albert.phases.phase_1_ambiguity_hunt import phase_1_ambiguity_hunt

def _amb(term): return {"term": term, "why_dangerous": "w", "precise_question": "p"}

def test_phase_1_keeps_exactly_three(monkeypatch):
    import albert.phases.phase_1_ambiguity_hunt as m
    monkeypatch.setattr(m, "call_claude",
        lambda **k: {"top_ambiguities": [_amb("a"), _amb("b"), _amb("c")]})
    state = {"proposal": {"body": "no spec, uncertain, high perf"}, "research": []}
    out = phase_1_ambiguity_hunt(state)
    assert len(out["top_ambiguities"]) == 3
    assert out["phase_1_complete"] is True
    assert out["phase_1_status"] == "passed"

def test_phase_1_stub_on_failure(monkeypatch):
    import albert.phases.phase_1_ambiguity_hunt as m
    def boom(**k): raise RuntimeError("llm down")
    monkeypatch.setattr(m, "call_claude", boom)
    state = {"proposal": {"body": "x"}, "research": []}
    out = phase_1_ambiguity_hunt(state)
    assert len(out["top_ambiguities"]) == 3   # stub still yields 3
    assert out["phase_1_status"] == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_phase_1_ambiguity.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `albert/phases/phase_1_ambiguity_hunt.py`**

```python
"""Phase 1 (bone 1): hunt vague terms, surface the 3 most dangerous."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas


def _stub_ambiguities() -> list[dict]:
    return [
        {"term": "(LLM unavailable)", "why_dangerous": "review could not run",
         "precise_question": "re-run Albert when transport is available"}
        for _ in range(3)
    ]


def _research_digest(research: list[dict], limit: int = 3) -> str:
    out = []
    for r in (research or [])[:limit]:
        out.append(f"- {r.get('query','')}: {str(r.get('results',''))[:300]}")
    return "\n".join(out)


def phase_1_ambiguity_hunt(state: dict) -> dict:
    context = (
        f"Proposal:\n{state['proposal'].get('body','')[:6000]}\n\n"
        f"Research facts:\n{_research_digest(state.get('research', []))}\n"
    )
    status = "passed"
    try:
        result = call_claude(
            model=model_for_role("ambiguity_hunt"),
            system=load_prompt("ambiguity_hunt"),
            user=context,
            json_schema=schemas.AMBIGUITY_HUNT,
            purpose="ambiguity_hunt",
        )
        top = result.get("top_ambiguities") or []
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_1 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        top, status = _stub_ambiguities(), "failed"

    # Defensive: enforce exactly 3.
    if not isinstance(top, list) or len(top) < 3:
        top = (top or []) + _stub_ambiguities()
    state["top_ambiguities"] = top[:3]
    state["phase_1_status"] = status
    state["phase_1_complete"] = True
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_phase_1_ambiguity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add albert/phases/phase_1_ambiguity_hunt.py tests/test_phase_1_ambiguity.py
git commit -m "feat: phase 1 ambiguity hunt (top-3 dangerous)"
```

---

## Task 8: Phase 2 — soul interrogation

**Files:**
- Create: `albert/phases/phase_2_soul_interrogation.py`
- Test: `tests/test_phase_2_soul.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase_2_soul.py
from albert.phases.phase_2_soul_interrogation import phase_2_soul_interrogation

def test_phase_2_generates_questions_and_merges_sharpenings(monkeypatch):
    import albert.phases.phase_2_soul_interrogation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"soul_questions": [
        {"q": "why win?", "generator": "winning", "bone": 2},
        {"q": "latency budget?", "generator": "timing", "bone": 5},
    ]})
    state = {"proposal": {"body": "x"}, "research": [], "top_ambiguities": [],
             "phase_3_rounds": [{"weaknesses": [
                 {"question_index": 0, "classification": "ADDRESSABLE",
                  "issue": "too generic", "suggested_sharpening": "tie to competitor roadmap"}]}]}
    out = phase_2_soul_interrogation(state)
    assert len(out["soul_questions"]) == 2
    assert out["phase_2_status"] == "passed"

def test_phase_2_stub_on_failure(monkeypatch):
    import albert.phases.phase_2_soul_interrogation as m
    def boom(**k): raise RuntimeError("down")
    monkeypatch.setattr(m, "call_claude", boom)
    state = {"proposal": {"body": "x"}, "research": [], "top_ambiguities": []}
    out = phase_2_soul_interrogation(state)
    assert out["phase_2_status"] == "failed"
    assert len(out["soul_questions"]) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_phase_2_soul.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `albert/phases/phase_2_soul_interrogation.py`**

```python
"""Phase 2 (bones 2-11): generate soul questions across the six generators.

On a rework loop (phase_3 -> phase_2) the prior round's ADDRESSABLE sharpenings
are fed back so regeneration is informed, not blind."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas


def _stub_questions() -> list[dict]:
    return [{"q": "(LLM unavailable — re-run Albert)", "generator": "winning", "bone": 2}]


def _prior_sharpenings(state: dict) -> str:
    rounds = state.get("phase_3_rounds") or []
    if not rounds:
        return ""
    last = rounds[-1]
    fixes = [w.get("suggested_sharpening", "")
             for w in last.get("weaknesses", [])
             if isinstance(w, dict) and w.get("classification") == "ADDRESSABLE"]
    fixes = [f for f in fixes if f]
    if not fixes:
        return ""
    return "Prior audit said these questions were too weak — sharpen them:\n" + \
           "\n".join(f"- {f}" for f in fixes) + "\n\n"


def _digest(items, key, limit=4):
    return "\n".join(f"- {str(i.get(key, i))[:200]}" for i in (items or [])[:limit])


def phase_2_soul_interrogation(state: dict) -> dict:
    context = (
        f"{_prior_sharpenings(state)}"
        f"Proposal:\n{state['proposal'].get('body','')[:6000]}\n\n"
        f"Dangerous ambiguities:\n{_digest(state.get('top_ambiguities'), 'term')}\n\n"
        f"Research facts:\n{_digest(state.get('research'), 'results', 3)}\n"
    )
    status = "passed"
    try:
        result = call_claude(
            model=model_for_role("soul_interrogation"),
            system=load_prompt("albert_persona") + "\n\n" + load_prompt("soul_interrogation"),
            user=context,
            json_schema=schemas.SOUL_INTERROGATION,
            purpose="soul_interrogation",
        )
        questions = result.get("soul_questions") or []
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_2 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        questions, status = _stub_questions(), "failed"

    if not isinstance(questions, list) or not questions:
        questions, status = _stub_questions(), "failed"
    state["soul_questions"] = questions
    state["phase_2_status"] = status
    state["phase_2_complete"] = True
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_phase_2_soul.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add albert/phases/phase_2_soul_interrogation.py tests/test_phase_2_soul.py
git commit -m "feat: phase 2 soul interrogation with rework-feedback"
```

---

## Task 9: Phase 3 — self-critique audit (exhaustion verdict)

**Files:**
- Create: `albert/phases/phase_3_self_critique_audit.py`
- Test: `tests/test_phase_3_audit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase_3_audit.py
from albert.phases.phase_3_self_critique_audit import phase_3_self_critique_audit

class _FakeSession:
    def __init__(self, audit): self._audit = audit
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def ask(self, user, purpose="x"): return self._audit

def _patch(monkeypatch, audit):
    import albert.phases.phase_3_self_critique_audit as m
    monkeypatch.setattr(m, "ClaudeSession", lambda **k: _FakeSession(audit))

def test_rework_when_addressable(monkeypatch):
    _patch(monkeypatch, {"round": 1, "verdict": "REWORK",
        "weaknesses": [{"classification": "ADDRESSABLE", "issue": "generic"}]})
    state = {"soul_questions": [{"q": "x"}]}
    out = phase_3_self_critique_audit(state)
    assert out["phase_3_verdict"] == "REWORK"
    assert out["phase_3_status"] == "passed"
    assert out["phase_3_attempt_count"] == 1

def test_exhausted_when_only_residual(monkeypatch):
    _patch(monkeypatch, {"round": 1, "verdict": "EXHAUSTED",
        "weaknesses": [{"classification": "RESIDUAL", "issue": "ask customer"}]})
    state = {"soul_questions": [{"q": "x"}]}
    out = phase_3_self_critique_audit(state)
    assert out["phase_3_verdict"] == "EXHAUSTED"

def test_fallback_marks_failed_and_forces_exhausted(monkeypatch):
    import albert.phases.phase_3_self_critique_audit as m
    class _Boom(_FakeSession):
        def ask(self, user, purpose="x"): raise RuntimeError("transport")
    monkeypatch.setattr(m, "ClaudeSession", lambda **k: _Boom(None))
    state = {"soul_questions": [{"q": "x"}]}
    out = phase_3_self_critique_audit(state)
    assert out["phase_3_status"] == "failed"
    assert out["phase_3_verdict"] == "EXHAUSTED"   # degraded audit may NOT drive a rework
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_phase_3_audit.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `albert/phases/phase_3_self_critique_audit.py`**

```python
"""Phase 3: adversarial self-critique of Albert's own soul questions.

Mirrors skill-ai-escape-mrc/phase_3_rc_audit: classify each question's weakness
ADDRESSABLE vs RESIDUAL, emit REWORK / EXHAUSTED. A degraded (fallback) audit is
never allowed to drive a rework (degraded-emission guard)."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import ClaudeSession
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas


def phase_3_self_critique_audit(state: dict) -> dict:
    state.setdefault("phase_3_rounds", [])
    system = load_prompt("self_critique_auditor")
    audit = None
    with ClaudeSession(
        system=system,
        model=model_for_role("self_critique_audit"),
        schema=schemas.SELF_CRITIQUE_AUDIT,
        allow_tools=True,
        max_turns=3,
        timeout_sec=240,
    ) as sess:
        user_msg = (
            "Audit these soul questions. Classify every weakness and give a verdict.\n\n"
            f"{json.dumps(state['soul_questions'], ensure_ascii=False)[:20000]}\n\n"
            "Use WebSearch if you need to check whether a question is research-backed."
        )
        try:
            audit = sess.ask(user_msg, purpose="self_critique_audit")
        except VisibilityContractError:
            raise
        except Exception as e:
            sys.stderr.write(f"[WARN] phase_3 audit failed: {type(e).__name__}: {str(e)[:200]}; fallback\n")
            audit = {"round": 1, "weaknesses": [], "verdict": "EXHAUSTED", "_fallback": True}

    if isinstance(audit, list):
        audit = audit[0] if (len(audit) == 1 and isinstance(audit[0], dict)) else \
                {"round": 1, "weaknesses": audit, "verdict": "EXHAUSTED", "_normalized": True}
    if not isinstance(audit, dict):
        audit = {"round": 1, "weaknesses": [], "verdict": "EXHAUSTED", "_fallback": True}

    state["phase_3_rounds"].append(audit)

    is_fallback = bool(audit.get("_fallback"))
    raw_verdict = audit.get("verdict")
    # Degraded audit may never drive a rework.
    verdict = "REWORK" if (not is_fallback and raw_verdict == "REWORK") else "EXHAUSTED"
    state["phase_3_verdict"] = verdict
    state["phase_3_status"] = "failed" if is_fallback else "passed"
    state["phase_3_attempt_count"] = state.get("phase_3_attempt_count", 0) + 1
    state["phase_3_complete"] = True
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_phase_3_audit.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add albert/phases/phase_3_self_critique_audit.py tests/test_phase_3_audit.py
git commit -m "feat: phase 3 adversarial self-critique with degraded guard"
```

---

## Task 10: Phase 4 — evidence gap + decision gate

**Files:**
- Create: `albert/phases/phase_4_gap_and_gate.py`
- Test: `tests/test_phase_4_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase_4_gate.py
from albert.phases.phase_4_gap_and_gate import phase_4_gap_and_gate

def test_phase_4_populates_gaps_and_gate(monkeypatch):
    import albert.phases.phase_4_gap_and_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {
        "evidence_gaps": [{"item": "roadmap", "who_can_answer": "public"}],
        "decision_gate": {"can_decide_now": ["scope"], "cannot_decide": ["price"],
                          "owners": [{"area": "latency", "owner": "TBD"}]},
        "reproducible_judgment": "checklist",
    })
    state = {"proposal": {"body": "x"}, "soul_questions": [{"q": "y"}]}
    out = phase_4_gap_and_gate(state)
    assert out["evidence_gaps"][0]["who_can_answer"] == "public"
    assert "scope" in out["decision_gate"]["can_decide_now"]
    assert out["phase_4_status"] == "passed"

def test_phase_4_stub_on_failure(monkeypatch):
    import albert.phases.phase_4_gap_and_gate as m
    def boom(**k): raise RuntimeError("down")
    monkeypatch.setattr(m, "call_claude", boom)
    state = {"proposal": {"body": "x"}, "soul_questions": []}
    out = phase_4_gap_and_gate(state)
    assert out["phase_4_status"] == "failed"
    assert "owners" in out["decision_gate"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_phase_4_gate.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `albert/phases/phase_4_gap_and_gate.py`**

```python
"""Phase 4 (bones 7, 9, 12): evidence gaps + decision gate + reproducible judgment."""
import json
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas

_STUB_GATE = {"can_decide_now": [], "cannot_decide": ["(LLM unavailable)"], "owners": []}


def phase_4_gap_and_gate(state: dict) -> dict:
    context = (
        f"Proposal:\n{state['proposal'].get('body','')[:4000]}\n\n"
        f"Soul questions:\n{json.dumps(state.get('soul_questions', []), ensure_ascii=False)[:12000]}\n"
    )
    status = "passed"
    try:
        result = call_claude(
            model=model_for_role("gap_and_gate"),
            system=load_prompt("gap_and_gate"),
            user=context,
            json_schema=schemas.GAP_AND_GATE,
            purpose="gap_and_gate",
        )
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_4 failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        result, status = {}, "failed"

    state["evidence_gaps"] = result.get("evidence_gaps") or []
    state["decision_gate"] = result.get("decision_gate") or dict(_STUB_GATE)
    state["reproducible_judgment"] = result.get("reproducible_judgment") or ""
    state["phase_4_status"] = status
    state["phase_4_complete"] = True
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_phase_4_gate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add albert/phases/phase_4_gap_and_gate.py tests/test_phase_4_gate.py
git commit -m "feat: phase 4 evidence gap + decision gate"
```

---

## Task 11: `albert/render.py` + Phase 5 verdict & emit (degraded guard)

**Files:**
- Create: `albert/render.py`
- Create: `albert/phases/phase_5_verdict_render.py`
- Create: `templates/albert_report_template.md`
- Test: `tests/test_phase_5_verdict.py`, `tests/test_degraded_guard.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_degraded_guard.py
import pytest
from albert.render import enforce_degraded_guard
from albert.errors import DegradedEmissionError

def test_failed_run_cannot_be_green():
    with pytest.raises(DegradedEmissionError):
        enforce_degraded_guard(run_status="failed", light="green")

def test_failed_run_downgrades_via_caller_contract():
    # green is forbidden; yellow/red allowed
    enforce_degraded_guard(run_status="failed", light="red")     # no raise
    enforce_degraded_guard(run_status="passed", light="green")   # no raise
```

```python
# tests/test_phase_5_verdict.py
from albert.phases.phase_5_verdict_render import phase_5_verdict_render

def _base_state(tmp_path, statuses):
    s = {"run_dir": str(tmp_path), "run_id": "run-test", "mode": "standalone",
         "proposal": {"title": "T", "body": "b"}, "top_ambiguities": [],
         "soul_questions": [{"q": "x", "generator": "winning", "bone": 2}],
         "evidence_gaps": [], "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
         "reproducible_judgment": "rj"}
    s.update(statuses)
    return s

def test_passed_run_emits_challenge_json_and_report(tmp_path, monkeypatch):
    import albert.phases.phase_5_verdict_render as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"verdict": "可推進", "light": "green", "readiness_delta": 1})
    monkeypatch.setattr(m, "send_email", lambda **k: "sent")
    state = _base_state(tmp_path, {f"phase_{i}_status": "passed" for i in range(5)})
    out = phase_5_verdict_render(state)
    assert out["run_status"] == "passed"
    assert out["light"] == "green"
    assert out["challenge_json_path"] and out["report_path"]

def test_failed_phase_downgrades_green_to_red(tmp_path, monkeypatch):
    import albert.phases.phase_5_verdict_render as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {"verdict": "可推進", "light": "green", "readiness_delta": 2})
    monkeypatch.setattr(m, "send_email", lambda **k: "sent")
    state = _base_state(tmp_path, {"phase_0_status": "passed", "phase_1_status": "failed",
                                   "phase_2_status": "passed", "phase_3_status": "passed",
                                   "phase_4_status": "passed"})
    out = phase_5_verdict_render(state)
    assert out["run_status"] == "failed"
    assert out["light"] != "green"   # guard downgraded it
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m pytest tests/test_degraded_guard.py tests/test_phase_5_verdict.py -v`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write `albert/render.py`**

```python
"""Render Albert's challenge to markdown + the cockpit JSON contract, and the
degraded-emission guard."""
import json
from pathlib import Path
from albert.errors import DegradedEmissionError


def enforce_degraded_guard(run_status: str, light: str) -> None:
    """A degraded run (run_status=='failed') may NOT emit a green light.
    Raises DegradedEmissionError so the caller downgrades to red (refuse)."""
    if run_status == "failed" and light == "green":
        raise DegradedEmissionError(
            "green light on a degraded run is forbidden (R13)", predicate="failed_run_green"
        )


def build_challenge(state: dict) -> dict:
    return {
        "top_ambiguities": state.get("top_ambiguities", []),
        "soul_questions": state.get("soul_questions", []),
        "evidence_gaps": state.get("evidence_gaps", []),
        "decision_gate": state.get("decision_gate", {"can_decide_now": [], "cannot_decide": [], "owners": []}),
        "verdict": state.get("verdict", "產品定義不完整"),
        "light": state.get("light", "red"),
        "readiness_delta": int(state.get("readiness_delta", 0)),
        "reproducible_judgment": state.get("reproducible_judgment", ""),
        "run_status": state.get("run_status", "failed"),
    }


def write_challenge_json(state: dict, run_dir: Path) -> str:
    path = Path(run_dir) / "albert_challenge.json"
    path.write_text(json.dumps(build_challenge(state), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


_LIGHT_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def render_report(state: dict) -> str:
    c = build_challenge(state)
    lines = [
        f"# Albert Review — {state.get('proposal', {}).get('title', '(untitled)')}",
        "",
        f"**Verdict:** {c['verdict']} {_LIGHT_EMOJI.get(c['light'], '')}  ·  "
        f"readiness_delta: {c['readiness_delta']}  ·  run_status: {c['run_status']}",
        "",
        "## 最危險的 3 個模糊點",
    ]
    for a in c["top_ambiguities"]:
        lines.append(f"- **{a.get('term','')}** — {a.get('why_dangerous','')}  → {a.get('precise_question','')}")
    lines += ["", "## 靈魂拷問"]
    for i, q in enumerate(c["soul_questions"], 1):
        lines.append(f"{i}. [{q.get('generator','')}/bone{q.get('bone','')}] {q.get('q','')}")
    lines += ["", "## 必須補的 Evidence"]
    for g in c["evidence_gaps"]:
        lines.append(f"- {g.get('item','')} — *who can answer:* {g.get('who_can_answer','')} "
                     f"({g.get('needed_before','')})")
    gate = c["decision_gate"]
    lines += ["", "## Decision Gate",
              f"- **現在能決定:** {', '.join(gate.get('can_decide_now', [])) or '(none)'}",
              f"- **現在不能決定:** {', '.join(gate.get('cannot_decide', [])) or '(none)'}",
              "- **Owners:** " + (", ".join(f"{o.get('area')}→{o.get('owner')}"
                                            for o in gate.get('owners', [])) or "(none)")]
    lines += ["", "## 可複用判斷", c["reproducible_judgment"] or "(none)"]
    return "\n".join(lines)


def write_report(state: dict, run_dir: Path) -> str:
    path = Path(run_dir) / "albert_review.md"
    path.write_text(render_report(state), encoding="utf-8")
    return str(path)
```

- [ ] **Step 4: Write `templates/albert_report_template.md`**

```markdown
# Albert Review — {title}

**Verdict:** {verdict} {light}  ·  readiness_delta: {readiness_delta}

## 最危險的 3 個模糊點
{ambiguities}

## 靈魂拷問
{soul_questions}

## 必須補的 Evidence
{evidence_gaps}

## Decision Gate
{decision_gate}

## 可複用判斷
{reproducible_judgment}
```

- [ ] **Step 5: Write `albert/phases/phase_5_verdict_render.py`**

```python
"""Phase 5: synthesize verdict + light, apply degraded guard, render + emit."""
import sys
from pathlib import Path
from albert.errors import VisibilityContractError, DegradedEmissionError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas
from albert.render import enforce_degraded_guard, write_challenge_json, write_report
from albert.email_delivery import send_email

_PHASE_STATUS_KEYS = ["phase_0_status", "phase_1_status", "phase_2_status",
                      "phase_3_status", "phase_4_status"]


def _run_status(state: dict) -> str:
    return "failed" if any(state.get(k) == "failed" for k in _PHASE_STATUS_KEYS) else "passed"


def phase_5_verdict_render(state: dict) -> dict:
    run_status = _run_status(state)
    state["run_status"] = run_status

    context = (
        f"Ambiguities: {state.get('top_ambiguities')}\n"
        f"Soul questions: {len(state.get('soul_questions', []))}\n"
        f"Evidence gaps: {state.get('evidence_gaps')}\n"
        f"Decision gate: {state.get('decision_gate')}\n"
    )
    try:
        v = call_claude(
            model=model_for_role("verdict_render"),
            system=load_prompt("verdict_render"),
            user=context,
            json_schema=schemas.VERDICT,
            purpose="verdict_render",
        )
        verdict, light = v.get("verdict", "要補證據"), v.get("light", "yellow")
        delta = int(v.get("readiness_delta", 0))
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_5 verdict failed: {type(e).__name__}: {str(e)[:200]}; refuse\n")
        verdict, light, delta, run_status = "產品定義不完整", "red", -2, "failed"
        state["run_status"] = run_status

    # Degraded guard: a failed run can never be green — downgrade to red (refuse).
    try:
        enforce_degraded_guard(run_status, light)
    except DegradedEmissionError:
        light = "red"
        if verdict == "可推進":
            verdict = "要補證據"

    state["verdict"], state["light"], state["readiness_delta"] = verdict, light, delta

    run_dir = Path(state["run_dir"])
    state["challenge_json_path"] = write_challenge_json(state, run_dir)
    state["report_path"] = write_report(state, run_dir)

    # Email only in standalone mode (cockpit consumes the JSON directly).
    if state.get("mode") == "standalone" and state.get("user_email"):
        try:
            state["email_delivery_result"] = send_email(
                to=state["user_email"],
                subject=f"[Albert] {verdict} — {state['proposal'].get('title','review')}",
                body_path=state["report_path"],
            )
        except Exception as e:
            state["email_delivery_result"] = "failed"
            state["email_delivery_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    state["phase_5_complete"] = True
    return state
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3 -m pytest tests/test_degraded_guard.py tests/test_phase_5_verdict.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add albert/render.py albert/phases/phase_5_verdict_render.py templates/albert_report_template.md tests/test_degraded_guard.py tests/test_phase_5_verdict.py
git commit -m "feat: phase 5 verdict + render + degraded-emission guard"
```

---

## Task 12: `albert/email_delivery.py`

**Files:**
- Create: `albert/email_delivery.py`
- Test: `tests/test_email_delivery.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email_delivery.py
import albert.email_delivery as ed

def test_send_email_returns_sent_when_transport_ok(monkeypatch, tmp_path):
    p = tmp_path / "r.md"; p.write_text("body", encoding="utf-8")
    monkeypatch.setattr(ed, "_send_via_outlook", lambda to, subject, body, cc: None)
    assert ed.send_email(to="a@b.com", subject="s", body_path=str(p)) == "sent"

def test_send_email_no_recipient_returns_skipped(tmp_path):
    p = tmp_path / "r.md"; p.write_text("body", encoding="utf-8")
    assert ed.send_email(to=None, subject="s", body_path=str(p)) == "skipped"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_email_delivery.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `albert/email_delivery.py`**

```python
"""Outlook COM email delivery (standalone mode only). Config from ~/.claude/email.json.

Mirrors the sibling skills' delivery pattern. Best-effort: returns a status
string rather than raising on transport failure, so a delivery problem never
loses the already-written report on disk."""
import json
from pathlib import Path

_EMAIL_CFG = Path.home() / ".claude" / "email.json"


def _load_cfg() -> dict:
    try:
        return json.loads(_EMAIL_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _send_via_outlook(to: str, subject: str, body: str, cc: str | None) -> None:
    import win32com.client  # pywin32; only imported on the real send path
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
    cc = cc or _load_cfg().get("operator_email")
    _send_via_outlook(to, subject, body, cc)
    return "sent"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_email_delivery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add albert/email_delivery.py tests/test_email_delivery.py
git commit -m "feat: standalone Outlook email delivery"
```

---

## Task 13: `albert/graph.py` — FSM wiring + conditional edge

**Files:**
- Create: `albert/graph.py`
- Test: `tests/test_graph_topology.py`, `tests/test_self_critique_loop.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graph_topology.py
from albert.graph import build_graph, _route_after_audit, _max_rework

def test_graph_compiles():
    g = build_graph()
    assert g is not None

def test_route_rework_under_cap_loops_back(monkeypatch):
    monkeypatch.delenv("ALBERT_MAX_REWORK", raising=False)
    state = {"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}
    assert _route_after_audit(state) == "phase_2_soul_interrogation"

def test_route_rework_over_cap_proceeds(monkeypatch):
    monkeypatch.setenv("ALBERT_MAX_REWORK", "2")
    state = {"phase_3_verdict": "REWORK", "phase_3_attempt_count": 3}
    assert _route_after_audit(state) == "phase_4_gap_and_gate"

def test_route_exhausted_proceeds():
    state = {"phase_3_verdict": "EXHAUSTED", "phase_3_attempt_count": 1}
    assert _route_after_audit(state) == "phase_4_gap_and_gate"

def test_max_rework_zero_disables_loop(monkeypatch):
    monkeypatch.setenv("ALBERT_MAX_REWORK", "0")
    assert _max_rework() == 0
    state = {"phase_3_verdict": "REWORK", "phase_3_attempt_count": 1}
    assert _route_after_audit(state) == "phase_4_gap_and_gate"
```

```python
# tests/test_self_critique_loop.py
"""End-to-end loop: REWORK twice, then EXHAUSTED, honoring the cap."""
from albert.graph import build_graph

def test_exhaustion_loop_runs_and_terminates(monkeypatch):
    import albert.phases.phase_0_intake_research as p0
    import albert.phases.phase_1_ambiguity_hunt as p1
    import albert.phases.phase_2_soul_interrogation as p2
    import albert.phases.phase_3_self_critique_audit as p3
    import albert.phases.phase_4_gap_and_gate as p4
    import albert.phases.phase_5_verdict_render as p5

    monkeypatch.setenv("ALBERT_MAX_REWORK", "2")
    # Phase 0/1: trivial stubs.
    monkeypatch.setattr(p0, "call_claude", lambda **k: {"queries": [], "facts": []})
    monkeypatch.setattr(p0, "websearch", lambda q: {"query": q, "results": ""})
    monkeypatch.setattr(p1, "call_claude", lambda **k: {"top_ambiguities":
        [{"term": "t", "why_dangerous": "w", "precise_question": "p"}] * 3})
    monkeypatch.setattr(p2, "call_claude", lambda **k: {"soul_questions":
        [{"q": "x", "generator": "winning", "bone": 2}]})

    # Phase 3: REWORK on attempts 1-2, EXHAUSTED on attempt 3.
    calls = {"n": 0}
    class _Sess:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ask(self, user, purpose="x"):
            calls["n"] += 1
            verdict = "REWORK" if calls["n"] < 3 else "EXHAUSTED"
            return {"round": calls["n"], "weaknesses": [], "verdict": verdict}
    monkeypatch.setattr(p3, "ClaudeSession", lambda **k: _Sess())

    monkeypatch.setattr(p4, "call_claude", lambda **k: {"evidence_gaps": [],
        "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
        "reproducible_judgment": "rj"})
    monkeypatch.setattr(p5, "call_claude", lambda **k: {"verdict": "可推進", "light": "green", "readiness_delta": 1})
    monkeypatch.setattr(p5, "send_email", lambda **k: "skipped")

    g = build_graph()
    state = {"albert_input": {"proposal": {"body": "b"}, "mode": "standalone"},
             "run_dir": str(monkeypatch.__class__ and __import__("tempfile").mkdtemp()),
             "run_id": "run-loop", "mode": "standalone"}
    final = g.invoke(state, config={"configurable": {"thread_id": "t", "recursion_limit": 100}})
    assert final["phase_5_complete"] is True
    assert calls["n"] == 3            # looped back twice then exhausted
    assert final["phase_3_attempt_count"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3 -m pytest tests/test_graph_topology.py tests/test_self_critique_loop.py -v`
Expected: FAIL — `albert.graph` not found.

- [ ] **Step 3: Write `albert/graph.py`**

```python
"""LangGraph StateGraph for the Albert reviewer FSM.

Topology:
  START
    -> phase_0_intake_research
    -> phase_1_ambiguity_hunt
    -> phase_2_soul_interrogation
    -> phase_3_self_critique_audit
        --[REWORK & attempt<=cap]--> phase_2_soul_interrogation
        --[else]-------------------> phase_4_gap_and_gate
    -> phase_5_verdict_render
    -> END
"""
import os
from functools import wraps
from langgraph.graph import StateGraph, START, END
from langgraph.errors import GraphInterrupt
from albert.state import AlbertState

from albert.phases.phase_0_intake_research import phase_0_intake_research
from albert.phases.phase_1_ambiguity_hunt import phase_1_ambiguity_hunt
from albert.phases.phase_2_soul_interrogation import phase_2_soul_interrogation
from albert.phases.phase_3_self_critique_audit import phase_3_self_critique_audit
from albert.phases.phase_4_gap_and_gate import phase_4_gap_and_gate
from albert.phases.phase_5_verdict_render import phase_5_verdict_render


def _max_rework() -> int:
    try:
        return max(0, int(os.environ.get("ALBERT_MAX_REWORK", "2")))
    except (TypeError, ValueError):
        return 2


def _route_after_audit(state: dict) -> str:
    if state.get("phase_3_verdict") == "REWORK" and state.get("phase_3_attempt_count", 0) <= _max_rework():
        return "phase_2_soul_interrogation"
    return "phase_4_gap_and_gate"


def _wrap_with_progress(name: str, fn):
    @wraps(fn)
    def wrapper(state):
        from albert import progress as _p
        from albert.stage_summary import emit_phase_error, emit_phase_start_summary, emit_stage_summary
        emit_phase_start_summary(name, state)
        _p.phase_start(name, {"state_keys": list(state.keys())[:20]})
        try:
            result = fn(state)
            if not isinstance(result, dict):
                raise TypeError(f"{name} must return dict state patch, got {type(result).__name__}")
            merged = dict(state); merged.update(result)
            result.update(emit_stage_summary(name, merged))
            _p.phase_end(name, {"ok": True})
            return result
        except GraphInterrupt:
            _p.emit(name, "phase_interrupt", {"reason": "awaiting_human_approval"}); raise
        except Exception as e:
            emit_phase_error(name, state, e)
            _p.emit(name, "phase_error", {"error": type(e).__name__, "message": str(e)[:300]}); raise
    return wrapper


def build_graph(checkpointer=None):
    g = StateGraph(AlbertState)
    g.add_node("phase_0_intake_research", _wrap_with_progress("phase_0_intake_research", phase_0_intake_research))
    g.add_node("phase_1_ambiguity_hunt", _wrap_with_progress("phase_1_ambiguity_hunt", phase_1_ambiguity_hunt))
    g.add_node("phase_2_soul_interrogation", _wrap_with_progress("phase_2_soul_interrogation", phase_2_soul_interrogation))
    g.add_node("phase_3_self_critique_audit", _wrap_with_progress("phase_3_self_critique_audit", phase_3_self_critique_audit))
    g.add_node("phase_4_gap_and_gate", _wrap_with_progress("phase_4_gap_and_gate", phase_4_gap_and_gate))
    g.add_node("phase_5_verdict_render", _wrap_with_progress("phase_5_verdict_render", phase_5_verdict_render))

    g.add_edge(START, "phase_0_intake_research")
    g.add_edge("phase_0_intake_research", "phase_1_ambiguity_hunt")
    g.add_edge("phase_1_ambiguity_hunt", "phase_2_soul_interrogation")
    g.add_edge("phase_2_soul_interrogation", "phase_3_self_critique_audit")
    g.add_conditional_edges(
        "phase_3_self_critique_audit",
        _route_after_audit,
        {"phase_2_soul_interrogation": "phase_2_soul_interrogation",
         "phase_4_gap_and_gate": "phase_4_gap_and_gate"},
    )
    g.add_edge("phase_4_gap_and_gate", "phase_5_verdict_render")
    g.add_edge("phase_5_verdict_render", END)
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m pytest tests/test_graph_topology.py tests/test_self_critique_loop.py -v`
Expected: PASS. (If `stage_summary` emitters have different names than `emit_phase_start_summary`/`emit_stage_summary`/`emit_phase_error`, align the import/call names with the copied `albert/stage_summary.py`.)

- [ ] **Step 5: Commit**

```bash
git add albert/graph.py tests/test_graph_topology.py tests/test_self_critique_loop.py
git commit -m "feat: FSM graph with exhaustion conditional edge"
```

---

## Task 14: `run_albert.py` CLI + SKILL.md + README

**Files:**
- Create: `run_albert.py`, `SKILL.md`, `README.md`

- [ ] **Step 1: Write `run_albert.py`**

```python
"""CLI entry point for the Albert reviewer FSM."""
import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from albert.graph import build_graph
from albert.input_adapter import build_input

RUNS_DIR = Path(__file__).parent / "runs"
RUN_RETENTION_DAYS = 30


def main():
    ap = argparse.ArgumentParser(prog="run_albert")
    ap.add_argument("proposal", nargs="?", help="Proposal text or path to a proposal file")
    ap.add_argument("--input", dest="input_json", help="albert_input.json (cockpit mode)")
    ap.add_argument("--json-out", action="store_true", help="Print only the albert_challenge.json path on stdout")
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

    from albert import progress as _progress
    _progress.init(run_dir)
    try:
        from albert import heartbeat as _heartbeat
        _heartbeat.start(run_dir, run_id)
    except Exception as e:
        sys.stderr.write(f"[run_albert] WARN: heartbeat failed: {e}\n")

    db_path = run_dir / "checkpoint.db"
    with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": run_id, "recursion_limit": 100}}
        if args.resume_id:
            initial = None
        else:
            albert_input = build_input(raw_text=args.proposal, input_json=args.input_json)
            initial = {"albert_input": albert_input, "mode": albert_input["mode"],
                       "run_id": run_id, "run_dir": str(run_dir), "user_email": args.user_email}
        try:
            final = graph.invoke(initial, config=config)
        except Exception as exc:
            sys.stderr.write(f"[Albert] Run failed: {type(exc).__name__}: {str(exc)[:300]}\n")
            return 1

    if not final.get("phase_5_complete"):
        sys.stderr.write(f"Run incomplete. Inspect {run_dir}\n"); return 2

    if args.json_out:
        print(final.get("challenge_json_path", ""))   # machine-consumable stdout for cockpit
    else:
        print("\n".join([
            f"[Albert] {final.get('verdict')} ({final.get('light')})  readiness_delta={final.get('readiness_delta')}",
            f"- Report: {final.get('report_path')}",
            f"- Challenge JSON: {final.get('challenge_json_path')}",
            f"- Email: {final.get('email_delivery_result') or '(not sent)'}",
        ]), file=sys.stderr)
        print(final.get("report_path", ""))            # stdout token = report path
    return 0


def _gc():
    cutoff = time.time() - RUN_RETENTION_DAYS * 86400
    if not RUNS_DIR.exists():
        return
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
description: Use when reviewing or auditing a product / architecture proposal (Gateway / PM / SYS1 / SYS2 / SYS3 / roadmap / customer strategy) and you need a high-standard war-room reviewer that forces decision quality rather than summarizing. Triggers on Albert review, war-room review, soul questions, 靈魂拷問, winning thesis, decision gate, feasibility challenge, competitor strategy review, will-it-win, readiness audit. LangGraph FSM-driven — intake+research, ambiguity hunt, soul interrogation, adversarial self-critique exhaustion loop, evidence gap + decision gate, verdict (可推進/要補證據/方向錯/產品定義不完整) + 紅黃綠燈.
execution_mode: both
---

# Albert — high-standard war-room reviewer (LangGraph-driven)

Albert does NOT praise and does NOT summarize. He forces decision quality: every
vague term gets a precise definition, every feature must justify "will it win?",
every architecture is pushed on first principles and latency, every strategy
needs an owner and a fallback. The phase order and exhaustion loop are enforced
by Python code, not markdown.

## Invocation

Standalone (review a proposal, get a report + email):

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py "<proposal text or file path>" --user-email you@example.com

Cockpit (programmatic — returns the challenge JSON path on stdout):

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py --input albert_input.json --json-out

Other flags: `--resume <run_id>`, `--gc`, `--dry-run`.

## Output

- `albert_challenge.json` — the schema-validated contract (`schemas/albert_challenge.schema.json`):
  3 dangerous ambiguities, the soul questions, evidence gaps (who_can_answer),
  decision gate (owners), verdict, light, readiness_delta.
- `albert_review.md` — human-readable report (standalone; also emailed).

## Integration contract (R17 seam)

The consumer (`skill-cn5-research-cos`) adapts Albert's `albert_challenge.json` to
its `Auditor` Protocol. Both schemas are producer-owned and live in `schemas/`.
Do not change them without re-running the cockpit closed-loop test.
```

- [ ] **Step 3: Write `README.md`** (concise: what Albert is, the 12 bones reference to the spec, how to run, how the FSM/exhaustion loop works, env vars `ALBERT_MAX_REWORK` / `ALBERT_FAST_MODEL`, link to the design spec).

- [ ] **Step 4: Verify `--dry-run` and the full suite**

Run: `py -3 run_albert.py --dry-run "test proposal"`
Expected: `Would invoke Albert with run_id=run-...`, exit 0

Run: `py -3 -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add run_albert.py SKILL.md README.md
git commit -m "feat: run_albert CLI (standalone + cockpit) + SKILL.md + README"
```

---

## Task 15: Symlink into ~/.claude/skills + smoke run

**Files:** none (environment wiring)

- [ ] **Step 1: Symlink the skill so Claude Code can discover it**

```powershell
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.claude\skills\skill-cn5-i-am-albert" -Target "D:\D-claude\skill-cn5-i-am-albert"
```

(Per project memory: all skills in `D:/D-claude/skills/skill-*` are symlinked to `~/.claude/skills/`. This skill lives at `D:/D-claude/skill-cn5-i-am-albert`; symlink it the same way.)

- [ ] **Step 2: Full test suite green**

Run: `py -3 -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 3: Commit any final fixups**

```bash
git add -A
git commit -m "chore: final fixups after full-suite green"
```

---

## Self-Review (completed)

**Spec coverage:**
- §1 dual consumer / producer-owned schemas → Tasks 4, 6 (`build_input`), 14 (`--json-out`).
- §2 12 bones + 6 generators + soul-grade criteria → Task 5 (`albert_persona.txt`), schema `generator` enum (Task 4), Task 8.
- §3 FSM phases 0-5 + conditional edge → Tasks 6-11, 13.
- §3 8 borrowed rebut mechanisms → Task 9 (adversarial auditor, ADDRESSABLE/RESIDUAL, degraded guard, exhaustion verdict), Task 13 (capped graph loop), Task 8 (in-place sharpening feedback).
- §4 output/input contracts → Task 4.
- §5 invocation + `ALBERT_MAX_REWORK`/`ALBERT_FAST_MODEL` → Tasks 13, 2, 14.
- §6 repo layout → all tasks (note: persona is `prompts/albert_persona.txt`, not `agents/` — single source, no drift; recorded as an intentional deviation from the spec's `agents/` line).
- §7 testing → every task is TDD; topology + self-critique loop + degraded guard + schema + email tests present.
- §8 open decisions → resolved: copy infra (not shared lib); strong roles = soul/audit/verdict; Phase 0 single-wave research.

**Placeholder scan:** README Task 14 Step 3 describes contents rather than full text — acceptable (prose doc, no executable contract). All code steps contain complete code.

**Type consistency:** `phase_x_status` keys, `model_for_role` roles (`soul_interrogation`/`self_critique_audit`/`verdict_render` strong), schema names (`AMBIGUITY_HUNT`/`SOUL_INTERROGATION`/`SELF_CRITIQUE_AUDIT`/`GAP_AND_GATE`/`VERDICT`/`ALBERT_CHALLENGE`/`ALBERT_INPUT`), `_route_after_audit` node names — all consistent across tasks.
