# Albert Soul — Design Spec v0.4

- **Skill:** `skill-cn5-i-am-albert`
- **Repo:** `github.com/oxydavid-maxx/skill-cn5-i-am-albert`
- **Date:** 2026-06-01
- **Status:** design (v0.4) — aligned to the consumer's **implemented** `Auditor` contract (`AuditResult`) after a full re-read of `skill-cn5-research-cos` PRODUCT-SPEC §0–30 + phase1-implementation-plan models
- **Consumer:** `skill-cn5-research-cos` (CN5 Chief-of-Staff Research Cockpit) — the **Albert Thought Agent** (PRODUCT-SPEC §6.3 / §20)

> **v0.4 change rationale.** v0.3 was a research-loop draft-answer auditor, but it
> invented its own output shape. Re-reading the cockpit's *implemented* model
> (`phase1-implementation-plan.md` line 277) showed the real binding target is the
> `AuditResult` Pydantic class with four **load-bearing** fields v0.3 missed:
> `recommended_next_action` (the Chief-of-Staff `Decision` enum), `rationale`,
> `verdict` (`AuditVerdict`), and `degraded: bool` (the cockpit's `gate.assert_audit_ran`
> refuses a terminal stop when `degraded=True`). v0.4 aligns the output to
> `AuditResult`, enriches the input per §20, and upgrades Albert from "auditor that
> reports signals" to a **chief-of-staff sparring partner** that, having challenged,
> recommends the next loop action (advisory; the cockpit still decides). The 12-bone
> soul, exhaustion self-critique loop, rule-grounded signals, and borrowed
> `skill-ai-escape-mrc` mechanisms are retained.

---

## 1. Purpose & Boundary

Albert is a **high-standard product / architecture war-room reviewer** — a BU-head
mind that does not praise and does not summarize, but forces **decision quality**.
Built as an **independent, separately-evolvable LangGraph FSM skill**.

**Unified operation (L1).** Albert always **audits a "current answer / position"** and
asks: *would this survive an Albert / leadership challenge? where is it weak? what
should be probed next, and what should the team do next?* (PRODUCT-SPEC §6.3 line 117
+ example). One pipeline:

- **cockpit mode (primary):** the cockpit's `albert_thought_audit_node` is a
  client/adapter that maps its `ResearchState` → `albert_input.json`, runs Albert,
  and maps `albert_challenge.json` → its `AuditResult` (the `Auditor` Protocol return
  type). Albert is the mock-replaceable real brain behind that Protocol.
- **standalone mode (secondary):** a raw proposal is wrapped as an un-challenged
  current answer; the same pipeline runs; the one-line verdict + traffic light are a
  standalone-only presentation layer derived from the same signals.

**Job separation (L5, refined in v0.4).** Albert **reports** the rule-grounded signals
**and recommends** the next loop action with a rationale (advisory; LLM-controlled per
§14). The cockpit's `cos_decision` node — deterministic staged gates + the
`anti_premature_checklist` (§10) — makes the **final** decision and **enforces** the
stop. Albert is the sparring partner, not the decider. Albert does **meta-research**
(find/confirm higher-level questions, SOTA framing) but never **object-research**
(answering the issue branches — the cockpit's researcher's job).

Albert is the **producer** and owns both interface schemas. The cockpit adapts via its
`Auditor` Protocol; Albert ships a mapping table + a reference mapping that proves the
output fills `AuditResult` (§6, R17 seam).

### Out of scope (YAGNI)
- Object-level research answering the issue branches.
- Making/enforcing the cockpit's final decision (Albert only recommends).
- Multi-customer matrices, historical-challenge DB, web UI.

---

## 2. The Soul — 12 Bones (retained)

Canonical persona in `albert/prompts/albert_persona.txt` (separately evolvable):

1. Force every vague term into a precise definition.
2. "Will it win?" of every feature (must-have / nice-to-have / overkill / parity; why we win; backup if customer won't buy).
3. Decompose to first principles (application → service → latency/deterministic/safety/availability → compute placement).
4. Chase local-vs-central compute (command-down vs signal-up; actuator / BLDC controller).
5. Latency / deterministic numbers to bring fantasy back to reality.
6. Reverse-engineer competitor strategy (segment; tech/cost/customer/legacy; last-gen benchmark; next-gen roadmap).
7. Force a single owner (no 多頭馬車; who decides; pre-feasibility; binding risk + fallback).
8. Separate internal central thesis from external framing.
9. Converge the war-room NOW (answerable now vs needs customer; 30-point version).
10. Ask spec + business + schedule together.
11. Red-team the central thesis (where wrong; who is the contrarian).
12. Chase reproducible judgment, not one-off answers.

Six generators: `winning` ②⑪ · `first_principle` ③④ · `timing` ⑤ · `competitor` ⑥ ·
`owner_business` ⑦⑧⑩ · `convergence_redteam` ⑨⑪⑫. **Soul-grade test:** a question must
(a) target decision quality not document completeness, (b) force a thesis, (c) be
research-backed.

---

## 3. Input — what Albert reads (L2 + §20)

The input absorbs the cockpit's `ResearchState` (§17). Loop signals are grounded in
real telemetry, not LLM-inferred. `schemas/albert_input.schema.json`:

```json
{
  "mode": "cockpit | standalone",
  "current_answer": "the draft answer / position Albert audits (REQUIRED)",
  "original_objective": "the original question/goal — used to detect drift",
  "meeting_context": "who is asking / what meeting / target audience",
  "output_purpose": "meeting_defense | decision_readiness | find_blockers | exec_memo",
  "issue_map": [ ... ],
  "challenge_map": [ {challenge, status, ...prior Albert challenges} ],
  "evidence": [ {claim, source, confidence, ...} ],
  "skeptic_output": ["counterarguments already raised by the Skeptic agent"],
  "source_critic_output": ["source-quality verdicts already raised by the Source Critic"],
  "readiness_scores": { "albert_challenge_readiness": 0, "decision_readiness": 0,
                        "research_exhaustion_readiness": 0, "human_bottleneck_clarity": 0 },
  "recent_research_actions": ["what the loop did in recent rounds"],
  "research_state": { "branches_explored": [], "branches_open": [], "rounds_so_far": 0,
                      "new_info_rate": "high|medium|low|unknown", "stage_summary": "..." },
  "proposal": {"title": "...", "body": "...", "domain": "..."}
}
```

- `current_answer` is REQUIRED. Standalone synthesizes it from `proposal.body` and
  leaves telemetry empty.
- **Loop position (canonical order Source Critic → Skeptic → Albert):** Albert audits
  the already-critiqued state. He **consumes** `skeptic_output` + `source_critic_output`
  and builds the BU-head layer on top — he does not redo their work.
- `output_purpose` (from preflight, §8.1) tunes which bones Albert leans on
  (e.g. `meeting_defense` → ⑪ red-team + would-survive; `find_blockers` → ⑦⑨ owner/convergence).
- When telemetry is absent (standalone / no `research_state` / no `readiness_scores`),
  the loop signals degrade to `grounded_in: inferred` + `low_confidence`.

---

## 4. Output — aligned to the cockpit's `AuditResult` (L3 + L4 + v0.4)

**Binding target (cockpit, implemented):**
```python
class AuditResult(BaseModel):
    verdict: AuditVerdict                 # clean | challenges | exhausted
    challenges: list[AlbertChallenge]     # §17 entry shape
    weak_points: list[str]
    premature_end_risk: Risk              # low | medium | high
    research_drift_risk: Risk
    recommended_next_action: Decision | None   # COS decision enum
    rationale: str
    degraded: bool                        # gate.assert_audit_ran refuses terminal_stop if True
```

Albert owns a **superset** contract (`schemas/albert_challenge.schema.json`) whose every
field maps to `AuditResult` (load-bearing) or to the fields the cockpit's own gap-audit
A2 plans to add (`missing_business_context`, `questions_albert_would_ask`,
`recommended_next_probe`, `readiness_score_delta`) — those ship now as enrichment:

```json
{
  "verdict": "clean | challenges | exhausted",
  "audited_answer": "...",
  "would_survive_leadership": true,

  "top_ambiguities": [ {term, why_dangerous, precise_question} ],            // exactly 3 (bone 1)

  "albert_challenges": [                                                     // §17 AlbertChallenge superset
    { "challenge", "why_albert_would_ask", "current_answer",
      "status": "answered|partially_answered|needs_external_research|needs_internal_data|needs_bu_judgment|needs_albert_decision|needs_source_validation|blocked",
      "confidence": "low|medium|high",
      "severity": "low|medium|high",                  // §20 axis: how damaging the challenge is
      "current_answer_strength": "weak|medium|strong",// §20 axis: how well the answer addresses it
      "evidence_refs": [], "missing_info": "", "blocking_owner": "",
      "next_action": "", "meeting_ready_response": "",
      "recommended_probe": "",                        // §20 per-challenge probe
      "generator": "winning|first_principle|timing|competitor|owner_business|convergence_redteam",
      "bone": 1 }
  ],

  "weak_points": ["..."],                                                    // list[str] to match AuditResult
  "missing_business_context": ["..."],
  "missing_evidence": [ {item, who_can_answer} ],
  "questions_albert_would_ask": ["..."],

  "premature_end_risk": {"level": "low|medium|high", "atoms": {...}, "grounded_in": "research_state|inferred", "low_confidence": false, "why": "..."},
  "research_drift_risk":  {"level": "low|medium|high", "atoms": {...}, "grounded_in": "...", "low_confidence": false, "why": "..."},
  "recommended_next_probe": [ {probe, why, kind: "meta|object", priority: 1} ],

  "recommended_next_action": "continue_research|branch|rerank|pull_human|push_human|synthesize|pause|terminal_stop",
  "rationale": "why this action, in one BU-head paragraph",

  "readiness_score_delta": 0,                                                // -2..+2 (overall)
  "reproducible_judgment": "...",                                            // bone 12
  "degraded": false,                                                         // = run had any phase fallback
  "run_status": "passed|failed",

  // standalone-only presentation:
  "verdict_standalone": "可推進|要補證據|方向錯|產品定義不完整",
  "light": "green|yellow|red"
}
```

### L4 — rule-grounded signals (retained, with v0.4 action-consistency)
- `premature_end_risk.level` ← `NOT(all §9.3 stop conditions met)`, computed by
  `albert/signals.py` over named atoms (telemetry-set objective atoms; LLM fills fuzzy
  ones). `research_drift_risk` and the `recommended_next_probe` ranking likewise.
- **`recommended_next_action` must be consistent with the signals** (a deterministic
  guard, not LLM whim): high `premature_end_risk` ⇒ action ∉ {synthesize, terminal_stop};
  high `research_drift_risk` ⇒ action ∈ {rerank, pull_human}; customer-only residual
  evidence dominates ⇒ {push_human, pull_human}. The LLM proposes the action + rationale;
  `signals.py` vetoes an inconsistent action and substitutes the signal-implied one.
- Guards: every signal carries `grounded_in` + `atoms`; **never silently downgrade** a
  telemetry-high atom; insufficient telemetry ⇒ `low_confidence` + `inferred`.
- **`degraded`** = any phase fell back (`*_status == failed`). A degraded run may not emit
  `light: green` and forces `verdict != clean`; the cockpit's gate consumes `degraded` to
  refuse a terminal stop.

---

## 5. Architecture — LangGraph FSM (L5)

```
START
  -> phase_0_intake_grounding     (parse §20 input; wave-1 → reflect meta-question → wave-2)
  -> phase_1_ambiguity_hunt       (bone ① ; top-3 dangerous ambiguities)
  -> phase_2_challenge_generation (bones ②-⑪ ; albert_challenges §17+§20 shape, builds on skeptic/source-critic
                                   output; + weak_points + missing_business_context + would_survive_leadership)
  -> phase_3_self_critique_audit  (adversarial; audits CHALLENGE SHARPNESS only)
       --[REWORK & attempt<=cap]--> phase_2_challenge_generation
       --[else]------------------> phase_4_signals_action_gate
  -> phase_4_signals_action_gate  (rule-grounded premature_end/drift/next_probe; recommended_next_action
                                   + rationale with action-consistency guard; decision gate; reproducible_judgment)
  -> phase_5_assemble_render      (verdict + degraded; assemble AuditResult-aligned contract;
                                   standalone verdict+light; report + email)
  -> END
```

| Phase | Bones | Mechanism |
|---|---|---|
| 0 Intake & Grounding | — | Parse §20 input (cockpit: current_answer + maps + readiness_scores + skeptic/source-critic output + research_state; standalone: wrap proposal). **Meta-research** wave-1 → reflect meta-question (`SEARCH_REFLECTION`) → wave-2. No object-research. |
| 1 Ambiguity Hunt | ① | Top-3 dangerous ambiguities in the current answer. |
| 2 Challenge Generation | ②-⑪ | `albert_challenges` in §17+§20 superset shape (status, confidence, **severity**, **current_answer_strength**, recommended_probe, meeting_ready_response …), **building on** skeptic/source-critic output (don't redo). Plus `weak_points` (list[str]), `missing_business_context`, `would_survive_leadership`. `output_purpose` tunes emphasis. Exhaustion — no fixed count. |
| 3 Self-Critique Audit | ⑪ | Adversarial auditor classifies each challenge sharp / ADDRESSABLE (→ regenerate) / RESIDUAL; verdict REWORK/EXHAUSTED; capped loop to Phase 2. Audits sharpness only. |
| 4 Signals · Action · Gate | ⑦⑨⑫ | Rule-grounded `premature_end_risk` / `research_drift_risk` + ranked `recommended_next_probe`. LLM proposes `recommended_next_action` (COS `Decision` enum) + `rationale`; **`signals.py` enforces action-consistency** with the signals. `decision_gate` (owners) + `reproducible_judgment`. |
| 5 Assemble & Render | output | Compute `verdict` (AuditVerdict) + `degraded`; assemble the AuditResult-aligned superset JSON. Standalone: derive `verdict_standalone` + `light` (degraded guard); render markdown report + email + stdout token. |

### Borrowed from `skill-ai-escape-mrc` (retained)
1. Adversarial auditor as a distinct role. 2. Challenge-before-verdict. 3. Exhaustion over
pass/fail. 4. ADDRESSABLE vs RESIDUAL. 5. Capped audit→regenerate graph edge. 6. In-place
sharpening feedback. 7. Degraded-emission guard (now also emits `degraded` for the cockpit
gate). 8. Persistent session + early exit. 9. `SEARCH_REFLECTION` wave-1→meta→wave-2.

---

## 6. The Seam — proving the `AuditResult` binding (L6)

Albert repo ships:
1. `schemas/albert_input.schema.json` (§3) and `schemas/albert_challenge.schema.json` (§4).
2. `docs/albert-cockpit-mapping.md` — Albert field → cockpit `AuditResult` field + the §6.3/§5.2 enrichment fields:

   | cockpit `AuditResult` field | Albert field |
   |---|---|
   | `verdict` (AuditVerdict) | `verdict` |
   | `challenges` (`list[AlbertChallenge]`) | `albert_challenges` (superset; extra axes ignored by the model, kept for §20) |
   | `weak_points` (`list[str]`) | `weak_points` |
   | `premature_end_risk` (Risk) | `premature_end_risk.level` |
   | `research_drift_risk` (Risk) | `research_drift_risk.level` |
   | `recommended_next_action` (Decision) | `recommended_next_action` |
   | `rationale` | `rationale` |
   | `degraded` | `degraded` |
   | *(enrichment, per gap-audit A2)* | `missing_business_context`, `questions_albert_would_ask`, `recommended_next_probe`, `readiness_score_delta`, signal `atoms`/`grounded_in` |

3. `albert/cockpit_contract.py` — `to_audit_result(challenge) -> dict` producing exactly
   the `AuditResult` field set (+ an `enrichment` sub-dict for the A2 fields).
4. `tests/test_cockpit_contract.py` — loads a golden `albert_challenge.json`, runs
   `to_audit_result`, asserts every `AuditResult` field is populated, `recommended_next_action`
   ∈ the `Decision` enum, `premature_end_risk`/`research_drift_risk` ∈ `Risk`, `verdict`
   ∈ `AuditVerdict`, and `degraded` is bool. **R17 closed-loop anchor on Albert's side.**

The `AuditResult`/`Decision`/`Risk`/`AuditVerdict` enums come from the committed
`phase1-implementation-plan.md`; the contract test catches drift early.

---

## 7. Invocation

```
py -3 run_albert.py "<proposal text or file>"               # standalone
py -3 run_albert.py --input albert_input.json --json-out    # cockpit (prints albert_challenge.json path)
py -3 run_albert.py --resume <run_id> | --gc | --dry-run
```

Env: `ALBERT_MAX_REWORK` (default 2), `ALBERT_FAST_MODEL`, email `~/.claude/email.json`,
reports `docs/albert-reviews/`. Language: match input (cockpit memo language is Chinese per §21).

---

## 8. Repo Layout

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
         test_prompts_present.py test_input_adapter.py test_phase_0..5 test_render_degraded_guard.py
         test_cockpit_contract.py test_email_delivery.py test_graph_topology.py test_self_critique_loop.py
```

---

## 9. Testing (test-first)
- Per-phase tests; topology (incl. Phase 3→2 edge); self-critique loop (REWORK→regenerate→EXHAUSTED, cap).
- `test_signals_grounding` — level == rule over atoms; telemetry-high never downgraded; absent telemetry ⇒ inferred + low_confidence.
- `test_action_consistency` — high premature_end ⇒ recommended_next_action ∉ {synthesize, terminal_stop}; high drift ⇒ ∈ {rerank, pull_human}; an inconsistent LLM action is vetoed and replaced.
- `test_render_degraded_guard` — failed run never emits `light: green`; `degraded` is set; `verdict != clean`.
- `test_cockpit_contract` — golden output → `AuditResult` field set complete; enums valid (`Decision`/`Risk`/`AuditVerdict`); `degraded` bool (R17 anchor).
- schema validation tests.

---

## 10. Open Decisions (resolve in writing-plans)
- Confirm the exact `AuditVerdict` enum values (`clean|challenges|exhausted` assumed) and
  `Decision` enum values against the cockpit code before freezing the contract test.
- Copy sibling infra (not shared lib). Strong roles: `challenge_generation`, `self_critique_audit`,
  `verdict_render`, and `signals_action_gate` (action recommendation is reasoning-heavy).
- Phase 0 meta-research depth: wave-1 + one reflection + wave-2.
- Whether `readiness_score_delta` is a single overall value (§6.3) or per-dimension — start
  single overall; revisit if the cockpit wants per-dimension nudges.
