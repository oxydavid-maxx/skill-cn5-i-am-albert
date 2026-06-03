# Albert Quality Fixes (evidence_refs · veto-coherence · rework default) — Design

**Date:** 2026-06-03
**Status:** approved (fix-all directive 2026-06-03)

Three independent, well-scoped quality fixes to the Albert skill, surfaced by Albert's own
dogfood runs. Each is small and isolated; bundled into one spec, executed task-by-task.

## Research grounding

- **Source attribution / groundedness** (FutureAGI, RankStudio, AWS RAG): best practice is
  system instructions that *require* the model to rely on provided context and cite the
  specific retrieved evidence (a "citation presence" requirement); a cited doc can be real yet
  not support the claim, so the citation must point at an identifiable unit.
- **ClaimCheck (arXiv 2503.21717)** — grounded LLM critiques must associate each weakness with
  the specific claim/evidence it disputes; models underperform when refs are absent. Directly
  motivates Fix #1 (give challenges citable `[Rk]` ids; let the self-critique verify them).
- **LLM rationale faithfulness (arXiv 2407.00219, FaithLM)** — LLM free-text rationales are
  frequently *unfaithful* to the actual decision process. Motivates Fix #2: when a deterministic
  rule overrides the action, the stated rationale must reflect the override, not the pre-veto
  proposal.

## Fix #1 — Populate `evidence_refs` (citable research)

**Problem:** Albert's 3-vote self-critique repeatedly flagged "evidence_refs 為空 / 挑戰把目標當
前提". Root cause: `phase_2_challenge_generation` injects research into the prompt as bare,
un-numbered result snippets (`Research:\n- <result>...`, only the first 3, truncated), so the
model has nothing stable to cite. The `evidence_refs` field exists in the schema
(`_CHALLENGE_ITEM`) and the prompt caps it at 2, but nothing tells the model WHAT to put there.

**Fix:**
- `phase_2`: add a pure helper `_research_refs(state) -> str` that enumerates ALL research as
  `[R1] <query> → <result truncated ~180>` lines (one per research item). Replace the current
  bare `Research:` block in the context with this enumerated block.
- `albert/prompts/challenge_generation.txt`: add an instruction — "For each challenge, set
  `evidence_refs` to the `[Rk]` id(s) from the Research section that ground or directly relate
  to it (at most 2; leave empty if none genuinely apply). Cite the id only (e.g. `R1`), not the
  text." Keep the existing ≤2 cap.
- `albert/deliberation.py` `render_challenges`: when a challenge has `evidence_refs`, add a card
  line `證據:R1, R3` (join the ids). Omit the line when empty.
- `phase_3_self_critique_audit`: build the research digest with the SAME `[Rk]` ids (reuse the
  helper) so a vote judging "research-backed" can map a challenge's cited `Rk` to a real finding.

**Non-goal:** evidence_refs stays OPTIONAL in the schema (not required) — forcing it would make
the LLM fabricate citations when none apply (the "real doc, unsupported claim" failure from the
research). The prompt encourages; the render + self-critique expose gaps.

## Fix #2 — Verdict narrative ↔ signal-veto coherence

**Problem:** `phase_4` computes `recommended_next_action` via `enforce_action_consistency`
(rule-engine veto), but `reproducible_judgment` is free LLM text that may still name the
pre-veto action. Observed: judgment said "建議 continue_research" while the enforced action was
`push_human` after the customer-only-evidence veto. Reader sees a contradiction (an unfaithful
rationale, per the faithfulness literature above).

**Fix:** In `phase_4_signals_action_gate`, after `recommended_next_action` is computed, if it
differs from the LLM's `proposed_next_action`, append a deterministic note to
`state["reproducible_judgment"]`:
`（註:LLM 原建議 {proposed},經訊號否決改為 {recommended}。）`. Deterministic, no LLM call.
`render_verdict` already renders `reproducible_judgment`, so the note shows in the card and the
JSON. When no veto fired (proposed == recommended), append nothing.

## Fix #3 — Standalone default `ALBERT_MAX_REWORK=1`

**Problem:** Default rework cap is 2 (`graph._max_rework`), giving standalone runs long,
high-variance wall-clock. Standalone is interactive; one rework pass is the better default.

**Fix:** In `run_albert.py`, when mode is `standalone` AND `ALBERT_MAX_REWORK` is not set in the
environment, set `os.environ["ALBERT_MAX_REWORK"] = "1"` before the graph is built. Cockpit mode
and any explicit `ALBERT_MAX_REWORK` are untouched. `graph._max_rework()` keeps its default 2 for
cockpit/unspecified.

## Testing

- **#1:** `_research_refs` returns `[R1] q → ...` lines for given research; phase_2 context (via
  a small extraction or by calling the helper) contains `[R1]`; `render_challenges` shows
  `證據:R1` when a challenge has `evidence_refs=["R1"]` and omits the line when empty; phase_3
  digest contains `[R1]`.
- **#2:** phase_4 appends the `（註:…）` note to `reproducible_judgment` when proposed≠recommended
  (e.g. proposed `synthesize`, premature=high → recommended `continue_research`), and appends
  nothing when proposed==recommended. (Stub the LLM call as existing phase_4 tests do.)
- **#3:** calling the run_albert default-setter with standalone + unset env yields
  `ALBERT_MAX_REWORK=1`; with cockpit OR an explicit env value, it is left unchanged.
- Full suite stays green.

## Files

- Modify: `albert/phases/phase_2_challenge_generation.py` (`_research_refs`, ctx),
  `albert/prompts/challenge_generation.txt`, `albert/deliberation.py` (`render_challenges`),
  `albert/phases/phase_3_self_critique_audit.py` (digest ids),
  `albert/phases/phase_4_signals_action_gate.py` (veto note),
  `run_albert.py` (standalone rework default).
- Tests: `tests/test_evidence_refs.py` (or extend existing), `tests/test_deliberation.py`
  (render 證據 line), `tests/test_signals.py`/phase_4 test (veto note),
  `tests/test_rework_default.py`.
- Unchanged: schemas (evidence_refs already present, stays optional), graph, cockpit contract.
