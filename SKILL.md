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

## Deliberation stream (always on)

Every run streams Albert's full reasoning chain live to the terminal and to
`runs/<run_id>/deliberation.md`: the research grounding, the generated challenges +
3 dangerous ambiguities, the **3-vote self-critique debate** with the ≥2-of-3
convergence ruling, any rework rounds, the signals/risk reasoning, and the final
verdict. Emission is **hard-required** — a soul phase that produces output without
emitting its deliberation block fails the run (`VisibilityContractError`).

Run **foreground, no `tee`, no redirect** so the transcript streams as it is produced:

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py "<proposal>"

## 看辯論過程(同事用)

在終端機直接跑就會**即時**看到辯論卡片(研究 → 拷問 → 三票辯論 → 重做 → 裁決):

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py "<你的提案>"

不需要任何環境設定 — 程式會自動用 UTF-8 顯示(Windows 也不會亂碼,也不會因編碼錯誤中斷)。
跑起來會先印一行「▼▼▼ 辯論過程(即時顯示)▼▼▼」,卡片就在下面一張張出現;每張卡片同時存到
`runs/<run_id>/deliberation.md`,跑完螢幕也會印出報告與辯論全文的路徑。想看即時就**不要**
`| tee`、`> file` 或丟背景跑 — 那會把即時畫面導走(完整內容仍在 deliberation.md)。
