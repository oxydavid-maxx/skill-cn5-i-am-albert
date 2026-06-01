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
