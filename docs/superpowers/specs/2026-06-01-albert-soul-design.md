# Albert Soul — Design Spec v0.3

- **Skill:** `skill-cn5-i-am-albert`
- **Repo:** `github.com/oxydavid-maxx/skill-cn5-i-am-albert`
- **Date:** 2026-06-01
- **Status:** design (v0.3) — re-scoped after auditing against the consumer spec `skill-cn5-research-cos/docs/spec/PRODUCT-SPEC.md` §5.2, §6.3, §9.3
- **Consumer:** `skill-cn5-research-cos` (CN5 Chief-of-Staff Research Cockpit) — the **Albert Thought Agent** (PRODUCT-SPEC §6.3)

> **v0.3 change rationale.** v0.2 built a one-shot Gateway proposal reviewer
> (verdict + traffic light). Auditing against the consumer spec showed the
> cockpit needs an **Albert Thought Agent** that audits a *current answer* inside
> a continuous research loop and emits stop/continue/drift judgment signals
> (`premature_end_risk`, `research_drift_risk`, `recommended_next_probe`, …).
> v0.3 re-scopes around that contract. The 12-bone soul, the exhaustion
> self-critique loop, and the borrowed `skill-ai-escape-mrc` rebut mechanisms are
> retained; the output contract, the phase behavior, and the input are reshaped.

---

## 1. Purpose & Boundary

Albert is a **high-standard product / architecture war-room reviewer** — a BU-head
mind that does not praise and does not summarize, but forces **decision quality**.
Built as an **independent, separately-evolvable LangGraph FSM skill**.

**L1 — one unified operation.** Albert always **audits a "current answer / position"**
and asks: *would this survive an Albert / leadership challenge? where is it weak?
what should be probed next?* (PRODUCT-SPEC §6.3 line 117 + example). There is **one
pipeline**, not two:

- **cockpit mode (primary):** the current answer = the cockpit's `draft_answer`,
  read together with the issue map / challenge map / evidence / `research_state`.
  Albert returns the Albert-Thought-Agent contract (challenges + weak points +
  risk signals + next probe + readiness delta).
- **standalone mode (secondary):** a raw Gateway / PM / SYS proposal is wrapped as
  an *un-challenged current answer*; the same pipeline runs. The one-line verdict
  (可推進 / 要補證據 / 方向錯 / 產品定義不完整) + traffic light become a
  **standalone-only presentation layer** derived from the same signals.

Albert is the **producer** and **owns both interface schemas** (`schemas/albert_input.schema.json`,
`schemas/albert_challenge.schema.json`). The cockpit adapts to them via its own
`Auditor` Protocol; Albert ships a mapping table + a reference mapping that proves
the output fills the cockpit's §6.3/§5.2 shape (see §6). This is the R17 seam.

### Out of scope (YAGNI)
- Object-level research that answers the issue branches (that is the cockpit
  researcher's job — see §2 the meta/object search line).
- Deciding the cockpit's continue/stop action (Albert *reports* the signals; the
  cockpit decides — §5 job separation).
- Multi-customer comparison matrices, historical-challenge DB, web UI.

---

## 2. The Soul — 12 Bones (retained from v0.2)

Canonical persona lives in `albert/prompts/albert_persona.txt` (separately
evolvable). The 12 behaviors (superset of the original 7-behavior prompt, mirrored
from the cockpit's `albert-integration.md`):

1. Force every vague term into a precise definition.
2. Ask "will it win?" of every feature (must-have / nice-to-have / overkill / parity; why we win; backup if customer won't buy).
3. Decompose to first principles (application → service → latency/deterministic/safety/availability → compute placement).
4. Chase local-vs-central compute (command-down vs signal-up; actuator / BLDC controller).
5. Use latency / deterministic numbers to bring fantasy back to reality.
6. Reverse-engineer competitor strategy (segment cut; tech/cost/customer/legacy; last-gen benchmark; next-gen roadmap).
7. Force a single owner (no 多頭馬車; who decides; pre-feasibility; binding risk + fallback).
8. Separate internal central thesis from external framing.
9. Converge the war-room NOW (answerable now vs needs customer; 30-point version).
10. Ask spec + business + schedule together (cost; cut features for price; feasibility for a commercial offer).
11. Red-team the central thesis (where most likely wrong; who is the contrarian).
12. Chase reproducible judgment, not one-off answers.

Six **question generators** (the 12 bones grouped): `winning` ②⑪ · `first_principle`
③④ · `timing` ⑤ · `competitor` ⑥ · `owner_business` ⑦⑧⑩ · `convergence_redteam` ⑨⑪⑫.

**Soul-grade test** (Phase 3 self-critique enforces): a question must (a) target
decision quality not document completeness, (b) force a thesis, (c) be
research-backed, not a generic template.

---

## 3. Input — what Albert reads (L2)

**L2 decision: loop signals are grounded in real telemetry, not LLM-inferred.**
The input contract therefore requires the cockpit to pass the research-state data
it already tracks (PRODUCT-SPEC §5.3 Readiness Board, Stage Summary, Issue Map).

`schemas/albert_input.schema.json`:

```json
{
  "mode": "cockpit | standalone",
  "current_answer": "the draft answer / position Albert audits (REQUIRED)",
  "original_objective": "the original question/goal — used to detect drift",
  "issue_map": [ ... ],
  "challenge_map": [ {challenge, status, ...prior Albert challenges} ],
  "evidence": [ {claim, source, confidence, ...} ],
  "research_state": {
    "branches_explored": ["..."],
    "branches_open": ["..."],
    "rounds_so_far": 0,
    "new_info_rate": "high | medium | low | unknown",
    "stage_summary": "..."
  },
  "proposal": {"title": "...", "body": "...", "domain": "..."}
}
```

- `current_answer` is REQUIRED. In standalone mode the input adapter synthesizes it
  from `proposal.body` (the proposal *is* an un-challenged current answer) and
  leaves `research_state` empty.
- When `research_state` is absent/empty (standalone, or a cockpit caller that did
  not supply telemetry), the loop signals (§4) degrade to
  `grounded_in: "inferred"` + `low_confidence` — they are never emitted as
  confident levels without grounding.

---

## 4. Output — the Albert-Thought-Agent contract (L3 + L4)

**L3 decision: Albert owns a clean superset contract** whose semantics cover the
cockpit's §6.3 nine outputs and §5.2 Challenge Map entry. The shared 8-value
`status` enum is reused verbatim (those values *are* Albert's judgment categories).
A mapping table (§6) keeps the adapter trivial.

`schemas/albert_challenge.schema.json`:

```json
{
  "audited_answer": "echo of the current answer Albert reviewed",
  "would_survive_leadership": true,
  "top_ambiguities": [ {term, why_dangerous, precise_question} ],   // exactly 3 (bone 1)

  "albert_challenges": [                                            // §5.2 entry shape
    {
      "challenge": "...",
      "why_albert_would_ask": "...",
      "current_answer": "what the audited answer says about this (or empty)",
      "status": "answered | partially_answered | needs_external_research | needs_internal_data | needs_bu_judgment | needs_albert_decision | needs_source_validation | blocked",
      "confidence": "low | medium | high",
      "missing_info": "...",
      "blocking_owner": "...",
      "next_action": "...",
      "meeting_ready_response": "...",
      "generator": "winning | first_principle | timing | competitor | owner_business | convergence_redteam",
      "bone": 1
    }
  ],

  "weak_points": [ {point, why_it_fails_in_a_meeting} ],
  "missing_business_context": [ "..." ],
  "missing_evidence": [ {item, who_can_answer} ],

  "premature_end_risk": {
    "level": "low | medium | high",
    "atoms": { "open_high_impact_challenges": 0, "new_info_rate": "low",
               "challenge_map_mostly_classified": true,
               "unresolved_are_human_data_decision_only": true,
               "meta_question_search_found_new_high_impact_angle": false },
    "grounded_in": "research_state | inferred",
    "why": "..."
  },
  "research_drift_risk": {
    "level": "low | medium | high",
    "atoms": { "current_focus_in_original_high_value_set": true,
               "high_value_branch_ignored": false },
    "grounded_in": "research_state | inferred",
    "why": "..."
  },
  "recommended_next_probe": [ {probe, why, kind: "meta", priority: 1} ],

  "readiness_score_delta": 0,                                       // -2..+2
  "reproducible_judgment": "the reusable checklist this audit leaves behind (bone 12)",
  "run_status": "passed | failed",

  // standalone-only presentation layer (derived, not core):
  "verdict": "可推進 | 要補證據 | 方向錯 | 產品定義不完整",
  "light": "green | yellow | red"
}
```

### L4 — how the loop signals are generated (credibility)
**Signals are rule-structured, not LLM-gestalt.** Each signal's `level` is a
function of named `atoms`, aligned to the cockpit's own §9.3 stop conditions so the
two sides reason from the same definition:

- `premature_end_risk` level ← `NOT(all §9.3 stop conditions met)`. The atoms map
  1:1 to §9.3: new sources repeat (`new_info_rate=low`), no new high-impact
  challenge / **meta-question** (`meta_question_search_found_new_high_impact_angle=false`),
  challenge map mostly classified, unresolved items are human/data/decision only.
  Telemetry sets the objective atoms; the LLM only fills fuzzy atoms ("is this
  challenge high-impact?") and writes `why`.
- `research_drift_risk` level ← current focus ∉ `original_objective`'s high-value
  set, or a high-value branch is ignored for a low-value one.
- `recommended_next_probe` ← open challenges ranked by (impact × answerability);
  ranking is deterministic, the per-item impact/answerability is LLM-judged.

Three guards:
1. Every signal carries `grounded_in` + `atoms` (audit trail; data vs guess).
2. **Never silently downgrade:** a telemetry-high atom cannot be talked down by the
   LLM; it may only be escalated or explained.
3. **Degraded guard (extended):** if `research_state` is insufficient, the signal is
   emitted as `low_confidence` + `grounded_in: inferred`, never a confident level;
   and a run with any `*_status == "failed"` may not emit `light: green`
   (`DegradedEmissionError` → downgrade).

---

## 5. Architecture — LangGraph FSM (L5)

Mirrors sibling skills: Pydantic state, single `StateGraph` + conditional edges,
Claude Agent SDK transport, heartbeat + progress + no-console receipts, email,
`--resume` checkpoint.

```
START
  -> phase_0_intake_grounding     (parse input; ai-escape wave-1 → reflect meta-question → wave-2)
  -> phase_1_ambiguity_hunt       (bone ① ; top-3 dangerous ambiguities in the current answer)
  -> phase_2_challenge_generation (bones ②-⑪ ; albert_challenges §5.2 shape + weak_points
                                   + missing_business_context + would_survive_leadership)
  -> phase_3_self_critique_audit  (adversarial; audits CHALLENGE SHARPNESS only)
       --[REWORK & attempt<=cap]--> phase_2_challenge_generation
       --[else]------------------> phase_4_signals_and_gate
  -> phase_4_signals_and_gate     (rule-structured premature_end/drift/next_probe; decision gate;
                                   reproducible_judgment)
  -> phase_5_assemble_render      (assemble superset contract; standalone verdict+light; report+email)
  -> END
```

| Phase | Bones | Mechanism |
|---|---|---|
| 0 Intake & Grounding | — | Parse input (cockpit: current_answer + maps + research_state; standalone: wrap proposal, research_state empty). **Meta-research** (L5.5): wave-1 web search (competitor / SOTA / domain) → reflect a higher-level meta-question (borrow `SEARCH_REFLECTION`) → wave-2 search. Produces meta-question framing for Phase 2. **Object-research is NOT done here** (cockpit's job). |
| 1 Ambiguity Hunt | ① | Top-3 most dangerous ambiguities in the current answer. |
| 2 Challenge Generation | ②-⑪ | Generate `albert_challenges` against the current answer in §5.2 entry shape (incl. 8-value `status` and a `meeting_ready_response` candidate). Plus `weak_points`, `missing_business_context`, `would_survive_leadership`. Research-backed. Exhaustion model — no fixed count. |
| 3 Self-Critique Audit | ⑪ reflexive | Adversarial auditor (borrowed from `rc_audit_agent`): classify each challenge `sharp` / `ADDRESSABLE` (too vague → regenerate) / `RESIDUAL`. Verdict `REWORK`/`EXHAUSTED`. **Audits challenge sharpness only** — signals (Phase 4) are rule-grounded by construction and need no LLM re-audit. ADDRESSABLE sharpenings fed back to Phase 2. |
| 3→2 edge | — | `REWORK` + `attempt <= ALBERT_MAX_REWORK` (default 2) → loop back; else → Phase 4. This is the exhaustion loop. |
| 4 Signals & Gate | ⑦⑨⑫ | Rule-structured `premature_end_risk` / `research_drift_risk` (atoms aligned to §9.3) + ranked `recommended_next_probe`; `decision_gate` (owners); `reproducible_judgment`. Each signal: `grounded_in` + `atoms`. |
| 5 Assemble & Render | output | Assemble the superset contract → `albert_challenge.json` (cockpit). Standalone: derive `verdict` + `light` from the same signals (degraded guard); render markdown report + email + stdout token. |

**Job separation (L5):** Albert *reports* `premature_end_risk=high`; the **cockpit
decides** whether to research more. Albert's internal loop (Phase 3→2) only sharpens
his own challenges — it never pads challenges to mimic research, and never runs
object-research.

### Borrowed from `skill-ai-escape-mrc` (retained)
1. Adversarial auditor as a distinct role (`rc_audit_agent` is Albert's archetype).
2. Challenge-before-verdict (Phase 3 before Phase 5).
3. Exhaustion model over pass/fail scoring.
4. ADDRESSABLE vs RESIDUAL classification.
5. Audit→regenerate as a capped graph conditional edge.
6. In-place sharpening feedback to the next round.
7. Degraded-emission guard (`*_status == passed` gates emission; extended to signal grounding).
8. Persistent session + quality-preserving early exit.
9. **`SEARCH_REFLECTION` wave-1 → meta-question → wave-2** (L5.5) for meta-research grounding.

---

## 6. The Seam — proving the contract (L6)

**L6 decision: the producer proves the seam.** Albert ships, and a contract test
verifies, that its output fills the cockpit's §6.3/§5.2 shape — rather than handing
the cockpit an unproven contract.

Albert repo ships:
1. `schemas/albert_input.schema.json` — §3 shape.
2. `schemas/albert_challenge.schema.json` — §4 superset shape.
3. `docs/albert-cockpit-mapping.md` — the mapping table:

   | cockpit §6.3 / §5.2 field | Albert field |
   |---|---|
   | `albert_challenges` | `albert_challenges` (same entry shape) |
   | `weak_points` | `weak_points` |
   | `missing_business_context` | `missing_business_context` |
   | `missing_evidence` | `missing_evidence` |
   | `questions_albert_would_ask` | `albert_challenges[].challenge` |
   | `premature_end_risk` | `premature_end_risk.level` (+ atoms appendix) |
   | `research_drift_risk` | `research_drift_risk.level` |
   | `recommended_next_probe` | `recommended_next_probe` |
   | `readiness_score_delta` | `readiness_score_delta` |
   | §5.2 Challenge Map entry | `albert_challenges[]` (1:1 field names) |

4. `albert/cockpit_contract.py` — a **reference mapping** `to_cockpit(challenge)` →
   `{albert_thought_agent_outputs, albert_challenge_map_entries}`.
5. `tests/test_cockpit_contract.py` — loads a golden `albert_challenge.json`, runs
   `to_cockpit`, asserts every §6.3 field is populated and every `status` is one of
   the 8 enum values. **This is the R17 closed-loop anchor on Albert's side.** The
   cockpit owns the production adapter + its own integration test.

The cockpit's §6.3/§5.2 field names come from the committed `PRODUCT-SPEC.md`; the
contract test catches drift early.

---

## 7. Invocation

```
py -3 run_albert.py "<proposal text or file>"               # standalone
py -3 run_albert.py --input albert_input.json --json-out    # cockpit (prints albert_challenge.json path)
py -3 run_albert.py --resume <run_id> | --gc | --dry-run
```

Env: `ALBERT_MAX_REWORK` (default 2), `ALBERT_FAST_MODEL` (opt-in fast non-strong
roles), email config `~/.claude/email.json`, reports dir `docs/albert-reviews/`.
Language: match input.

---

## 8. Repo Layout

```
skill-cn5-i-am-albert/
  SKILL.md  README.md  requirements.txt  run_albert.py
  albert/
    __init__.py
    no_console.py errors.py utils.py progress.py heartbeat.py stage_summary.py sdk_client.py  (copied infra)
    models.py state.py schemas.py render.py email_delivery.py
    input_adapter.py          # raw proposal | cockpit json -> albert_input shape
    cockpit_contract.py       # reference mapping albert_challenge -> cockpit §6.3/§5.2
    graph.py
    prompts/
      albert_persona.txt intake_grounding.txt search_reflection.txt ambiguity_hunt.txt
      challenge_generation.txt self_critique_auditor.txt signals_and_gate.txt verdict_render.txt
    phases/
      phase_0_intake_grounding.py phase_1_ambiguity_hunt.py phase_2_challenge_generation.py
      phase_3_self_critique_audit.py phase_4_signals_and_gate.py phase_5_assemble_render.py
  schemas/ albert_input.schema.json  albert_challenge.schema.json
  templates/ albert_report_template.md
  docs/
    albert-cockpit-mapping.md
    albert-reviews/
    superpowers/specs/2026-06-01-albert-soul-design.md
  tests/
    test_graph_topology.py test_self_critique_loop.py test_degraded_guard.py
    test_signals_grounding.py        # premature_end/drift level == rule over atoms; never-downgrade
    test_albert_input_schema.py test_albert_challenge_schema.py
    test_cockpit_contract.py         # R17 seam anchor
    test_input_adapter.py test_phase_0..5 test_email_delivery.py
```

---

## 9. Testing (test-first)
- Per-phase tests; `test_graph_topology` (incl. Phase 3→2 edge); `test_self_critique_loop`
  (REWORK→regenerate→EXHAUSTED, cap honored).
- `test_signals_grounding` — `premature_end_risk.level` is the rule over its atoms;
  a telemetry-high atom is never downgraded; absent `research_state` ⇒
  `grounded_in: inferred` + `low_confidence`.
- `test_degraded_guard` — failed run never emits `light: green`.
- `test_albert_input_schema` / `test_albert_challenge_schema` — contract validation.
- `test_cockpit_contract` — golden output maps to §6.3/§5.2 with all statuses in the
  8-value enum (R17 anchor).

---

## 10. Open Decisions (resolve in writing-plans)
- Copy sibling infra vs extract shared lib → **copy** (sibling precedent).
- Strong model roles → `challenge_generation`, `self_critique_audit`, `verdict_render`.
- Phase 0 meta-research depth → wave-1 + one reflection + wave-2 (mirror ai-escape);
  escalate only if grounding proves shallow.
- `research_state.new_info_rate` source: cockpit-provided enum vs derived from
  `branches_explored` deltas → start with cockpit-provided enum, fall back to
  `unknown`.
