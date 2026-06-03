# Albert Quick Mode (~5 min, ~80% quality) — Design

**Date:** 2026-06-03
**Status:** approved (directive 2026-06-03: sacrifice quality to ~80, cut to ~5 min)

## Goal

A third run profile **`quick`** targeting **≈5 min at ~80% quality**, alongside `thorough`
(default) and `fast`. Free-tier only — speed comes from **cutting**, deliberately.

## Why quick must change the graph (not just knobs)

Benchmark (fast run): phase_0 research = 296s; the Opus chain (p2 + p3 + p4 + p5) = 539s ≈ 9 min,
made of **sequential Opus rounds**. Knobs alone can't reach 5 min — the round COUNT is the cost.
Quick therefore **collapses the analysis into one Opus call** and **skips the separate 3-vote
self-critique debate (p3) and the separate signals/verdict round (p4)**. This is the soul cost:
no multi-vote exhaustion debate, no rework. That is the ~80%.

## Time budget (estimate)

- phase_0: intake call (~30s) + minimal research (3 queries, 1 batch, turns=3) ~150s → ~180s
- one combined analysis call (challenges + inline self-critique + verdict) ~150s
- p5 render ~0
- **≈330s ≈ 5.5 min** (target ≤6, aim 5). The benchmark verifies; if >6, cut research to 2
  queries / cap challenges to 5.

## Design

### Selection / profile

- `albert/profile.py` gains `quick`: `--quick` flag + `ALBERT_PROFILE=quick`. `resolve_profile`
  returns `thorough|fast|quick`. `QUICK_DEFAULTS`:
  `ALBERT_MAX_REWORK=0`, `ALBERT_WEBSEARCH_MAX_TURNS=3`, `ALBERT_RESEARCH_WIDTH=3`,
  `ALBERT_RESEARCH_MAX_QUERIES=3`. (setdefault — explicit env wins.)
- `run_albert` resolves the profile and puts it into the initial graph state as `state["profile"]`
  so the graph can route on it. `--quick` and `--fast` are mutually exclusive (if both, `--quick`
  wins with a stderr note).

### Graph routing (profile-gated)

`albert/graph.py`: a conditional edge AFTER phase_0:
- `state["profile"] == "quick"` → `phase_quick_combined` → `phase_5_assemble_render` → END.
- else → `phase_2_challenge_generation` → … (unchanged thorough/fast path).

The quick node is added with the same `_wrap` (so deliberation `assert_emitted` + progress still
apply).

### New phase: `albert/phases/phase_quick_combined.py`

ONE Opus call that does, in a single pass: the 3 dangerous ambiguities + capped challenges
(~6) + an **inline self-critique** instruction (the model critiques its own challenges in the
same response) + the signals atoms + the verdict presentation (verdict_standalone / light /
readiness_score_delta) + proposed action + rationale + reproducible_judgment.

- **Schema** = merge of the existing `schemas.CHALLENGE_GENERATION` properties and
  `schemas.SIGNALS_VERDICT_MERGED` properties (both already exist) into one `QUICK_COMBINED`
  schema. No new contract fields.
- **Prompt** = `albert_persona` + a new `quick_combined.txt` that fuses challenge_generation +
  signals_action_gate guidance, adds "cap to ~6 high-impact challenges; include a one-line
  self-critique per challenge (is it sharp / research-backed); be concise", and the 繁體中文
  directive.
- **After the call (deterministic, reuse `signals.py`)** — identical to phase_4's tail:
  `premature_end_level` / `drift_level` on the atoms → `build_risk(..., why=premature_end_why/…)`
  → `state["premature_end_risk"]` / `state["research_drift_risk"]`;
  `enforce_action_consistency(proposed, …)` → `state["recommended_next_action"]` (+ the veto note
  from the earlier fix). Set `albert_challenges`, `weak_points`, `top_ambiguities`,
  `would_survive_leadership`, `verdict_standalone`, `light`, `readiness_score_delta`, `rationale`,
  `reproducible_judgment`, `recommended_next_probe`, `missing_evidence`, `decision_gate`,
  `verdict="exhausted"` (single pass, no rework), `run_status`. On LLM failure → a `_stub` like the
  other phases (degraded path intact).
- **Deliberation:** emit a `phase_quick_combined` block — header `PHASE Q ─ 快速審查(quick)`,
  the ambiguities + challenge cards (reuse `deliberation.render_challenges`), a short "inline
  self-critique" line, then the verdict (reuse `deliberation.render_signals` + `render_verdict`).
  Must satisfy `assert_emitted("phase_quick_combined")`.

To DRY the deterministic signals tail, extract phase_4's lines into a shared helper
`albert/signals_apply.py::apply_signals(state, res)` (sets the risk/action/verdict state from a
result dict) and call it from BOTH phase_4 and phase_quick_combined.

### phase_0 research cap

New knob `ALBERT_RESEARCH_MAX_QUERIES` (default: current behavior = no extra cap, i.e. the
existing `[:8]`). `phase_0` slices `queries[:_research_max_queries()]` where the helper returns
`int(env)` or a large default (8). Quick sets it to 3. Thorough/fast unchanged (8).

### Cockpit contract

Quick still emits the full `ALBERT_CHALLENGE` contract (verdict/challenges/risks/action/…), so
`cockpit_contract.to_audit_result` + `tests/test_cockpit_contract.py` keep passing unchanged.

## Non-goals

- No paid infra (no Opus fast-mode / search backend assumptions).
- Not removing the debate from thorough/fast — only quick skips it.
- Not a new contract/schema field — reuse existing schemas + signals.py.

## Testing

- `profile`: `resolve_profile` returns "quick" for `--quick` / `ALBERT_PROFILE=quick`;
  `apply_profile("quick", env)` sets the 4 QUICK_DEFAULTS (setdefault).
- `graph`: route-after-intake returns `phase_quick_combined` when `state["profile"]=="quick"`,
  else `phase_2_challenge_generation`. A quick graph compiles and has the quick→p5 edge.
- `phase_quick_combined` (LLM stubbed like other phase tests): populates albert_challenges +
  verdict_standalone + premature_end_risk(.why) + recommended_next_action; emits a deliberation
  block; degraded stub path on call failure.
- `signals_apply.apply_signals` unit test (atoms in → risk/action/verdict state out); phase_4
  still green after refactor.
- `_research_max_queries`: default 8; env "3" → 3; bad → 8.
- cockpit contract test still green from a quick-shaped state.
- Benchmark (run task): quick vs thorough/fast on the same proposal → wall-clock + quality into
  `docs/speedup-results.md`; target ≤6 min (aim 5) and a ~80% quality note (challenges present +
  a verdict; debate intentionally absent).

## Files

- Modify: `albert/profile.py` (+quick, QUICK_DEFAULTS), `run_albert.py` (--quick, profile→state,
  mutual-exclusion), `albert/graph.py` (quick node + conditional route after p0),
  `albert/phases/phase_0_intake_grounding.py` (`_research_max_queries`),
  `albert/phases/phase_4_signals_action_gate.py` (use `apply_signals`), `albert/schemas.py`
  (`QUICK_COMBINED`), `SKILL.md`, `docs/speedup-results.md` (benchmark).
- Create: `albert/phases/phase_quick_combined.py`, `albert/signals_apply.py`,
  `albert/prompts/quick_combined.txt`, tests (`test_quick_profile`, `test_quick_route`,
  `test_phase_quick_combined`, `test_signals_apply`, `test_research_max_queries`).
- Unchanged: cockpit contract schema, deliberation/redirect-refusal, models routing, thorough/fast paths.
