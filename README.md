# skill-cn5-i-am-albert — Albert Thought Agent

Albert is a high-standard product & architecture war-room reviewer — a BU-head mind.
He does **not** praise and does **not** summarize. He audits a **current answer** to
force *decision quality*: would it survive a leadership challenge, where is it weak,
what should be probed next, and what should the team do next.

This skill is the implementation of the CN5 cockpit's **Albert Thought Agent**: a
LangGraph FSM that takes a current answer (or a raw proposal) and returns a contract
that maps 1:1 to the cockpit's `AuditResult` — challenges, weak points, rule-grounded
stop/drift signals, a recommended next action, rationale, and a `degraded` flag.

## The 12 bones (Albert's persona)

The persona is defined by twelve "bones" — the reflexes Albert applies to any answer.
A question is **soul-grade** only if it targets decision quality (not document
completeness), forces a thesis, is research-backed, and probes **durability** (the moat
test: is the advantage durable or will it be copied/commoditized?).

1. Force every vague term into a precise definition.
2. Ask "will it win?" of every feature (must-have / nice-to-have / overkill / parity).
3. Decompose to first principles (application → service → latency/deterministic/safety/availability → compute placement).
4. Chase local-vs-central compute (command-down vs signal-up; actuator / BLDC controller).
5. Use latency / deterministic numbers to bring fantasy back to reality.
6. Reverse-engineer competitor strategy (segment; tech/cost/customer/legacy; last-gen benchmark; next-gen roadmap).
7. Force a single owner (no 多頭馬車; who decides; pre-feasibility; binding risk + fallback).
8. Separate internal central thesis from external framing.
9. Converge the war-room NOW (answerable now vs needs customer; 30-point version).
10. Ask spec + business + schedule together.
11. Red-team the central thesis (where wrong; who is the contrarian).
12. Chase reproducible judgment, not one-off answers.

Full persona + soul-grade durability clause: `albert/prompts/albert_persona.txt`.
Authoritative spec: [`docs/superpowers/specs/2026-06-01-albert-soul-design.md`](docs/superpowers/specs/2026-06-01-albert-soul-design.md) (v0.4.1).

## Invocation

Cockpit (programmatic — prints the challenge JSON path on stdout):

    py -3 run_albert.py --input albert_input.json --json-out

Standalone (review a proposal text or file → markdown report + optional email):

    py -3 run_albert.py "<proposal text or file>" --user-email you@example.com

Other flags:

- `--resume <run_id>` — resume a crashed/checkpointed run from the last successful
  stage (LangGraph SqliteSaver checkpoint under `runs/<run_id>/checkpoint.db`); never
  re-runs from stage 0.
- `--gc` — prune `runs/` directories older than 30 days.
- `--dry-run` — print `Would invoke Albert with run_id=run-...` and exit 0 without
  running the graph (smoke check).

## Architecture — FSM + multi-vote exhaustion loop

Albert is a six-phase `StateGraph` with one conditional edge:

- **Phase 0 — intake + meta-research grounding.** Normalize the input, then run a
  wave-1 → reflect → wave-2 *meta* search (what a mature SOTA product would do,
  competitor next-gen roadmap, public latency/cost benchmarks). Meta-research only —
  researching the issue branches themselves is the cockpit's job.
- **Phase 1 — ambiguity hunt** (bone 1): the three most *dangerous* vague terms.
- **Phase 2 — challenge generation** (bones 2–11): soul-grade, research-backed
  challenges, each with severity + current-answer-strength, built on the Skeptic's and
  Source Critic's prior output.
- **Phase 3 — self-critique audit.** An **adversarial** auditor of Albert's own
  challenges. To avoid the self-critique paradox, this is **multi-vote** (N=3, ≥2 must
  agree). Each weakness is classified `addressable` (sharpen it) or `residual` (only the
  customer can resolve). Verdict `rework` if any addressable weakness remains →
  **conditional edge back to Phase 2** for another round; `exhausted` when every
  remaining weakness is residual; `continue` if more research is warranted. The loop is
  bounded by `ALBERT_MAX_REWORK` (default 2).
- **Phase 4 — signals + action gate.** The LLM emits the loop-signal **atoms**, a
  **proposed** next action, and the decision gate. The deterministic rule engine
  computes the final risk **levels** and may **veto** an inconsistent action (see below).
- **Phase 5 — assemble + render.** Build the `albert_challenge.json` contract + the
  markdown report; enforce the degraded-emission guard (a degraded run cannot ship a
  non-refusal verdict or green light).

## Rule-grounded signals + recommended next action

Loop signals are **never** an LLM gestalt. `albert/signals.py` is a deterministic rule
engine over named atoms (aligned to consumer §9.3):

- `premature_end_risk` — high when the "safe to stop" conditions are not all met
  (0 violations → low, 1 → medium, ≥2 → high).
- `research_drift_risk` — based on whether the current focus is in the original
  high-value set and whether a high-value branch was ignored.

The `recommended_next_action` is LLM-**proposed** but **vetoed for consistency** with
the signals via `enforce_action_consistency` (precedence: premature > drift > evidence):
high premature_end blocks `synthesize`/`terminal_stop` → `continue_research`; high drift
forces `rerank`/`pull_human`; ≥2 customer-only residual evidence items force
`push_human`. **Albert recommends; the cockpit still decides.**

## Environment variables

- `ALBERT_MAX_REWORK` — max Phase 3 → Phase 2 rework rounds (default 2).
- `ALBERT_FAST_MODEL` — route non-reasoning-heavy roles (e.g. ambiguity hunt, intake
  grounding) to a faster model. The strong roles (challenge generation, self-critique
  audit, signals/action gate, verdict render) always stay on the session default.

## Cockpit seam (R17)

The seam to the COS cockpit is contract-pinned and tested:

- `schemas/albert_input.schema.json`, `schemas/albert_challenge.schema.json` — the wire
  format on both sides of the seam.
- `docs/albert-cockpit-mapping.md` — the field-by-field mapping from Albert's output to
  the cockpit's `AuditResult`.
- `albert/cockpit_contract.py` — the `to_audit_result` transform that produces the
  cockpit-shaped payload.
- `tests/test_cockpit_contract.py` — proves the seam (R17). Do **not** change the
  schemas without re-running this test **and** the cockpit's integration test.
