# Albert → Cockpit `AuditResult` Mapping (R17 seam)

This document defines how Albert's output contract (`albert_challenge.json`, schema
`schemas/albert_challenge.schema.json`) maps 1:1 onto the cockpit's implemented
`AuditResult`. It is the human-readable companion to the **executable reference**
`albert/cockpit_contract.py::to_audit_result`, and `tests/test_cockpit_contract.py`
is the **R17 closed-loop anchor on Albert's side**.

The consumer is `skill-cn5-research-cos` (the CN5 Chief-of-Staff Research Cockpit),
which embeds Albert as its **Albert Thought Agent** (PRODUCT-SPEC §6.3 / §20). The
cockpit owns the production-side adapter; `to_audit_result` is the producer-side proof
that the field set and enums line up.

## Field mapping (spec §6)

| cockpit `AuditResult` field | Albert field | Notes |
|---|---|---|
| `verdict` (AuditVerdict) | `verdict` | enum `continue \| exhausted \| rework` |
| `challenges` (`list[AlbertChallenge]`) | `albert_challenges` | superset; extra axes (severity, current_answer_strength, generator, bone, high_impact, recommended_probe) ignored by the cockpit model, kept for §20 |
| `weak_points` (`list[str]`) | `weak_points` | coerced to strings |
| `premature_end_risk` (Risk) | `premature_end_risk.level` | enum `low \| medium \| high` (rule-grounded) |
| `research_drift_risk` (Risk) | `research_drift_risk.level` | enum `low \| medium \| high` (rule-grounded) |
| `recommended_next_action` (Decision) | `recommended_next_action` | enum `continue_research \| branch \| rerank \| pull_human \| push_human \| synthesize \| pause \| terminal_stop` (LLM-proposed, signal-vetoed) |
| `rationale` | `rationale` | |
| `degraded` | `degraded` | bool; a degraded run may not emit a green light |

### Enrichment (gap-audit A2 — fields the cockpit's `AuditResult` does not yet carry)

`to_audit_result` returns these under a separate `enrichment` sub-dict so the cockpit
can adopt them incrementally without breaking the load-bearing `audit_result` field set:

| enrichment field | Albert source |
|---|---|
| `missing_business_context` | `missing_business_context` |
| `questions_albert_would_ask` | `questions_albert_would_ask` |
| `recommended_next_probe` | `recommended_next_probe` (priority-ranked) |
| `readiness_score_delta` | `readiness_score_delta` |
| `premature_end_atoms` | `premature_end_risk.atoms` |
| `grounded_in` | `premature_end_risk.grounded_in` (`research_state` vs `inferred`) |

## Per-challenge entry (`AlbertChallenge`)

`to_audit_result._entry` projects each `albert_challenges` item down to the cockpit's
`AlbertChallenge` field set:

`challenge`, `why_albert_would_ask`, `current_answer`, `status` (8-value `ChallengeStatus`),
`confidence`, `evidence_refs`, `missing_info`, `blocking_owner`, `next_action`,
`meeting_ready_response`.

## Frozen enums

`AuditVerdict` / `Decision` / `Risk` / `ChallengeStatus` are frozen against the committed
`skill-cn5-research-cos/docs/superpowers/plans/2026-06-01-phase1-implementation-plan.md`.
They are re-exported in `albert/state.py` (`AUDIT_VERDICTS`, `DECISIONS`, `RISK_LEVELS`,
`CHALLENGE_STATUSES`) and asserted by `tests/test_cockpit_contract.py`, which catches enum
drift early.

## R17 discipline

Do **not** change `schemas/albert_challenge.schema.json` or `to_audit_result` without
re-running `tests/test_cockpit_contract.py` **and** the cockpit's integration test, then
recording a passing closed-loop entry for the contract. This seam is the integration
contract between Albert (producer) and the cockpit (consumer).
