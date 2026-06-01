# Albert Soul — Design Spec v0.2

- **Skill:** `skill-cn5-i-am-albert`
- **Repo:** `github.com/oxydavid-maxx/skill-cn5-i-am-albert`
- **Date:** 2026-06-01
- **Status:** design approved, pending spec review → writing-plans
- **Consumer:** `skill-cn5-research-cos` (CN5 Chief-of-Staff Research Cockpit) via its `Auditor` Protocol adapter

---

## 1. Purpose & Boundary

Albert is a **high-standard product / architecture war-room reviewer**, made into an
**independent, separately-evolvable LangGraph FSM skill**. His job is **not** to praise,
**not** to summarize a meeting — it is to **force decision quality**: to push a proposal
until it can no longer escape the questions of *why this wins*, *first principles*,
*timing*, *competitor strategy*, *owner*, *fallback*, and *business*.

Two consumers:

- **cockpit (programmatic):** feeds `albert_input.json` → receives schema-validated
  `albert_challenge.json`. The cockpit's `albert_thought_audit_node` is a client/adapter
  that maps Albert's rubric output → `AlbertChallenge[]` + readiness deltas.
- **human (standalone):** drops a Gateway / PM / SYS proposal (file or pasted text) →
  receives a markdown report + email + stdout report-path token.

Albert is the **producer** and **owns both interface schemas** (`schemas/albert_input.schema.json`,
`schemas/albert_challenge.schema.json`). They live in this repo; the cockpit adapts to them.
This is the integration seam R17 closed-loop watches.

### Out of scope (YAGNI for v0.1)
- Multi-customer comparison matrices
- Historical-challenge tracking DB
- Web UI / dashboard

---

## 2. The Soul — 12 Bones

The canonical persona lives in `agents/albert_persona.md` (separately evolvable). It is the
authoritative 12-behavior capture (superset of the original 7-behavior prompt), mirrored from
the cockpit's `albert-integration.md`:

1. Force every vague term into a precise definition ("no spec" = no high-level / implementation
   / customer-requirement / winning spec?).
2. Ask "will it win?" of every feature (must-have / nice-to-have / overkill / competitor-parity;
   why we win; backup if customer won't buy).
3. Decompose product to first principles (application → service → latency/deterministic/safety/
   availability → compute placement).
4. Chase local-vs-central compute until it can't be dodged (command-down vs signal-up;
   actuator / BLDC controller).
5. Use latency / deterministic to bring fantasy back to reality (latency budget numbers,
   ADC→compute→PWM path, network-latency=0 justification).
6. Reverse-engineer competitor strategy (segment cut; tech/cost/customer/legacy; are we
   benchmarking last gen; next-gen roadmap).
7. Force a single owner (no 多頭馬車; who decides; what must be answered pre-feasibility;
   binding risk + fallback).
8. Separate internal central thesis from external framing (discovery/alignment/commitment/
   negotiation; what to tell vs only listen).
9. Converge war-room NOW (answerable by AI/public/internal know-how now vs truly needs
   customer; 30-point version now).
10. Ask spec + business + schedule together (cost impact; cut features for lowest price;
    feasibility ready for commercial offer).
11. Red-team the central thesis (where most likely wrong; market/tech/customer/cost/schedule/
    ecosystem; who is the contrarian).
12. Chase reproducible judgment, not one-off answers (what reusable judgment / checklist this
    leaves behind).

### Question generators (the 12 bones grouped into 6)
Soul questions are **generated** by walking these generators against the specific proposal,
**grounded in Phase 0 research**:

| Generator | Bones |
|---|---|
| `winning` | ②⑪ |
| `first_principle` (incl. compute placement) | ③④ |
| `timing` (latency / deterministic) | ⑤ |
| `competitor` | ⑥ |
| `owner_business` (owner + business + schedule + external framing) | ⑦⑧⑩ |
| `convergence_redteam` (converge + red-team + reproducible judgment) | ⑨⑪⑫ |

### What makes a question "soul-grade" (acceptance criteria for Phase 3 self-critique)
1. **Targets decision quality, not document completeness.** ❌ "Is the latency field filled?"
   ✅ "What justifies network-latency=0? If it isn't 0, does your deterministic budget still hold?"
2. **Forces a thesis, not a feature list.** Every question converges to winning-thesis /
   first-principle / owner / fallback.
3. **Research-backed, not a template.** ✅ "Competitor X's next-gen roadmap already moved compute
   to the zone controller; you're benchmarking their *last* gen — why do you still win?"
   A question that any reviewer could ask without domain research is **too vague → regenerate**.

---

## 3. Architecture — LangGraph FSM

Mirrors sibling skills (`skill-8d-mrc`, `skill-ai-escape-mrc`): Pydantic state, single
`StateGraph` + conditional edges, Claude Agent SDK transport, heartbeat + progress +
no-console visibility receipts, email delivery, `--resume` checkpoint.

```
START
  -> phase_0_intake_research      (dual-mode parse + web research grounding)
  -> phase_1_ambiguity_hunt       (bone ① ; top-3 dangerous ambiguities)
  -> phase_2_soul_interrogation   (bones ②–⑪ ; generate challenges, research-backed)
  -> phase_3_self_critique_audit  (adversarial; classify each challenge; verdict)
       --[REWORK & attempt<=cap]--> phase_2_soul_interrogation   (regenerate weak challenges)
       --[else]------------------> phase_4_gap_and_gate
  -> phase_4_gap_and_gate         (bones ⑦⑨⑫ ; evidence gaps + decision gate)
  -> phase_5_verdict_render       (verdict + light + render + emit)
  -> END
```

### Phase detail

| Phase | Name | Bones | Mechanism |
|---|---|---|---|
| 0 | Intake & Research | — | Dual-mode input (standalone file/text OR cockpit `albert_input.json`). Web research: competitor segment/roadmap + public data to **ground** the interrogation (without research, soul questions degrade to templates). |
| 1 | Ambiguity Hunt | ① | Surface all vague terms → select the **3 most dangerous** (term / why_dangerous / precise_question). |
| 2 | Soul Interrogation | ②–⑪ | Walk the 6 generators; produce challenges grounded in Phase 0 research. **Exhaustion model — no fixed count.** |
| 3 | Self-Critique Audit | ⑪ reflexive | **Adversarial auditor** (borrowed from `rc_audit_agent`): for each challenge classify `sharp` / `ADDRESSABLE` (too vague → regenerate) / `RESIDUAL` (inherent — only the customer can sharpen). Emit verdict `REWORK` / `EXHAUSTED`. ADDRESSABLE fixes applied in-place as notes so the next round sees the corrected challenge. |
| 3→2 | conditional edge | — | `REWORK` + `attempt_count <= ALBERT_MAX_REWORK` (default 2) → loop back to Phase 2 to regenerate the weak challenges; else → Phase 4. This **is** the exhaustion loop: challenge until only RESIDUALs remain. |
| 4 | Evidence Gap + Decision Gate | ⑦⑨⑫ | Each evidence gap classified by `who_can_answer`: `AI` / `public` / `internal` (= answerable now, ADDRESSABLE) vs `customer` (= RESIDUAL until asked). Decision gate: `can_decide_now` / `cannot_decide` / `owners`. Reproducible-judgment leave-behind (bone ⑫). |
| 5 | Verdict & Render | output format ⑤ | Synthesize `verdict` (可推進 / 要補證據 / 方向錯 / 產品定義不完整) + `light` (🟢🟡🔴) → **degraded-emission guard**: if any phase fell back due to transport/LLM error (`*_status == "failed"`), **never emit a green light — refuse rather than ship a self-exonerating warning**. Render markdown report (standalone) + `albert_challenge.json` (cockpit) + email + stdout token. |

### Borrowed from `skill-ai-escape-mrc` rebut flow (deep-dive findings)
1. **Adversarial auditor as a distinct role** — `rc_audit_agent` is literally Albert's archetype
   ("You do NOT agree easily").
2. **Challenge-before-verdict** — Albert never lights green/yellow/red before he has actually
   interrogated (Phase 3 must run before Phase 5).
3. **Exhaustion model over pass/fail scoring** — no "7/10"; instead, challenge until no
   ADDRESSABLE weakness remains. A passing score hides weaknesses behind a threshold.
4. **ADDRESSABLE vs RESIDUAL classification** — maps directly to evidence-gap `who_can_answer`.
5. **Audit→regenerate as a graph conditional edge (capped)** — not an inline phase.
6. **In-place fix accumulation** — weak challenges get correction notes; next round sees them.
7. **Degraded-emission guard** — `*_status == "passed"` gates emission; fallback runs cannot
   drive a rework or ship a verdict.
8. **Persistent session across rounds** + **quality-preserving early exit** (stop on EXHAUSTED
   or convergence, not a fixed round count).

---

## 4. Output Contract — `schemas/albert_challenge.schema.json`

StructuredOutput-enforced (Claude CLI constrained decoding). Quality floor = schema validation:
fields present, enum values correct, counts correct, else retry.

```json
{
  "top_ambiguities": [
    {"term": "...", "why_dangerous": "...", "precise_question": "..."}
  ],
  "soul_questions": [
    {"q": "...", "generator": "winning|first_principle|timing|competitor|owner_business|convergence_redteam",
     "bone": 1, "grounding": "research ref or internal-knowledge basis"}
  ],
  "evidence_gaps": [
    {"item": "...", "who_can_answer": "AI|public|internal|customer", "needed_before": "..."}
  ],
  "decision_gate": {
    "can_decide_now": ["..."],
    "cannot_decide": ["..."],
    "owners": [{"area": "...", "owner": "..."}]
  },
  "verdict": "可推進|要補證據|方向錯|產品定義不完整",
  "light": "green|yellow|red",
  "readiness_delta": 0,
  "reproducible_judgment": "checklist / reusable judgment this review leaves behind",
  "run_status": "passed|failed"
}
```

Constraints:
- `top_ambiguities`: exactly 3.
- `soul_questions`: **variable length** (exhaustion model). The cockpit adapter maps this array
  to `AlbertChallenge[]` regardless of length, so a variable count is frictionless.
- `verdict`: one of the 4 enum values. `light`: one of green/yellow/red.
- `readiness_delta`: integer in `[-2, 2]` — the cockpit maps it onto its readiness_score.
- `run_status`: `failed` ⇒ `light` must not be `green` (degraded-emission guard, enforced in code
  + asserted in tests).

### Input Contract — `schemas/albert_input.schema.json`
Albert-owned shape that absorbs the cockpit's §20 input (issue map / challenge map / evidence /
draft answer / readiness). Standalone mode synthesizes this same shape from a raw proposal.

```json
{
  "proposal": {"title": "...", "body": "...", "domain": "..."},
  "issue_map": [],
  "challenge_map": [],
  "evidence": [],
  "draft_answer": "...",
  "readiness": 0,
  "mode": "standalone|cockpit"
}
```

These two schemas resolve the cockpit's three open integration-contract items (invocation,
request/response JSON, adapter mapping).

---

## 5. Invocation

```
py -3 run_albert.py "<proposal text or file path>"        # standalone
py -3 run_albert.py --input albert_input.json --json-out  # cockpit (prints albert_challenge.json path)
py -3 run_albert.py --resume <run_id>
py -3 run_albert.py --gc
py -3 run_albert.py --dry-run
```

Environment:
- `ALBERT_MAX_REWORK` (default 2) — self-critique rework cap; `0` disables looping (linear, faster).
- Email config from `~/.claude/email.json` (shared sibling convention).
- Reports dir defaults to `docs/albert-reviews/` (overridable via env), since this repo is the producer.

Language: **match input** (the persona is CN/EN mixed; preserve it).

---

## 6. Repo Layout

```
skill-cn5-i-am-albert/
  SKILL.md                         # name + description + execution_mode: both
  README.md
  run_albert.py                    # CLI entrypoint, --resume
  requirements.txt
  albert/
    __init__.py
    graph.py                       # StateGraph + conditional edges
    state.py                       # Pydantic AlbertState
    models.py                      # model_for_role
    schemas.py                     # StructuredOutput JSON schemas (challenge + per-phase)
    sdk_client.py                  # Claude Agent SDK transport (sibling-shared pattern)
    render.py                      # markdown report
    heartbeat.py / progress.py / no_console.py / utils.py / errors.py / validators.py
    phases/
      phase_0_intake_research.py
      phase_1_ambiguity_hunt.py
      phase_2_soul_interrogation.py
      phase_3_self_critique_audit.py
      phase_4_gap_and_gate.py
      phase_5_verdict_render.py
  agents/
    albert_persona.md              # the 12-bone soul (separately evolvable)
    self_critique_auditor.md       # adversarial self-review persona
  schemas/
    albert_input.schema.json       # producer-owned input contract
    albert_challenge.schema.json   # producer-owned output contract
  templates/
    albert_report_template.md
  tests/
    test_graph_topology.py
    test_phase_0.py ... test_phase_5.py
    test_self_critique_loop.py     # REWORK→regenerate→EXHAUSTED, cap honored
    test_albert_input_schema.py
    test_albert_challenge_schema.py
    test_degraded_guard.py         # failed run never emits green
    test_email_delivery.py
  docs/
    superpowers/specs/2026-06-01-albert-soul-design.md
    albert-reviews/                # standalone report output
```

---

## 7. Testing (test-first)
- One `test_phase_N.py` per phase.
- `test_graph_topology.py` — START→…→END wiring incl. the Phase 3→2 conditional edge.
- `test_self_critique_loop.py` — REWORK loops back, regenerates, honors `ALBERT_MAX_REWORK` cap,
  reaches EXHAUSTED.
- `test_albert_input_schema.py` / `test_albert_challenge_schema.py` — contract validation (the
  R17 seam); these are the closed-loop anchors against the cockpit.
- `test_degraded_guard.py` — a run with any `*_status == "failed"` cannot emit `light: green`.
- `test_email_delivery.py` — standalone email path.

---

## 8. Open Decisions (resolve in writing-plans)
- Exact Claude Agent SDK transport reuse: copy sibling `sdk_client.py` vs extract a shared lib.
- Per-phase model assignment (`model_for_role`) — which phases warrant Opus vs Sonnet.
- Whether Phase 0 research is single-wave or dual-tier (8D-style) — start single-wave; escalate
  only if grounding proves too shallow.
