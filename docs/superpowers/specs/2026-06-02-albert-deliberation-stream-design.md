# Albert Deliberation Stream — Design

**Date:** 2026-06-02
**Status:** approved (design dialogue 2026-06-02)
**Author:** Albert skill maintainer

## Problem

Albert produces a strong audit, but the user **cannot see the deliberation** — the
war-room reasoning that produces the verdict. The `[progress]` stream (fixed when we
removed `tee`) shows only phase markers (`phase_3 phase_end`). The actual debate —
the three self-critique votes attacking the challenge set, the convergence ruling, the
rework decisions, the challenge generation rationale — happens **inside the LLM calls**
and only the final structured verdict surfaces. The debate IS captured in state
(`phase_3_rounds` = the votes + per-weakness findings) but is **never emitted** to
anything the user can read.

User directive 2026-06-02: "辯論過程我還是沒看到。我說要改成硬需求." — make the
deliberation visible, as a **hard requirement** (not optional logging).

Two design axes were resolved with the user:
- **Scope of "debate":** the **full reasoning chain** — challenge generation →
  self-critique debate → rework → final verdict (not just the self-critique step).
- **"See it" means:** **live during the run** — the transcript streams to the
  terminal block-by-block as it is produced, not a dump at the end.

## Goal

Albert emits its full reasoning chain as a live, human-readable transcript the user
watches while the run executes, and emitting it is **structurally hard-required**: a
soul phase that produces output but stays silent fails the run (fail-closed), the same
enforcement class Albert already applies to its progress/visibility receipts.

## Non-goals (YAGNI)

- **No multi-voice debate engine.** We do not add a proposer/red-team/judge round-table
  (the user explicitly chose the reasoning-chain option, not the new-engine option).
- **No new LLM calls.** The deliberation is *rendered from structured output that
  already exists*. The debate content is already in `phase_3` votes and `phase_2`
  challenges; we were simply not rendering it.
- **No schema changes for v1.** If the rendered debate reads thin in dogfood, enriching
  the vote schema with a per-vote one-line stance is a deferred follow-up.

## Architecture

One new emission module + per-phase render calls + contract enforcement in the graph
wrapper. Mirrors the existing `albert/progress.py` + `albert/stage_summary.py`
visibility-receipt pattern, inheriting its fail-closed `VisibilityContractError`
discipline.

### Component 1 — `albert/deliberation.py`

A module-level singleton like `progress.py`:

- `init(run_dir: Path)` — opens `runs/<run_id>/deliberation.md`, resets the
  emitted-phase set. Raises `VisibilityContractError` if the dir can't be created.
- `block(phase: str, title: str, body: str)` — appends a markdown section
  (`\n## <title>\n\n<body>\n`) to `deliberation.md` **and** writes it to `stderr` with
  `flush=True` immediately, prefixed so it reads inline among `[progress]` lines (e.g.
  a `\n━━━ DELIBERATION — <title> ━━━\n<body>\n`). Records `phase` in the emitted set.
  Raises `VisibilityContractError` if either sink fails (fail-closed, like progress).
- `assert_emitted(phase: str)` — raises `VisibilityContractError(phase=...)` if the
  phase emitted no block. Called by the graph wrapper after each soul phase.
- `emitted(phase: str) -> bool` — predicate used by tests and `assert_emitted`.

Each phase renders itself (the phase owns its narrative voice). The module is a dumb,
fail-closed sink.

### Component 2 — per-phase render-and-emit (no new LLM calls)

Each soul phase, after it has its structured result, builds a narrative block from that
result and calls `deliberation.block(...)`:

- **phase_0_intake_grounding:** "要 audit 這個 thesis,我得先查什麼" → the research plan,
  the queries fired, and a 1-line digest per finding (from `state["research"]`).
- **phase_2_challenge_generation:** the 3 dangerous ambiguities (`top_ambiguities`),
  then each challenge rendered as `bone #N · why_albert_would_ask · challenge ·
  severity · current_answer_strength`. On a rework pass, prefix "Round N (rework)".
- **phase_3_self_critique_audit (the core 辯論):** for each of the 3 votes, list its
  weaknesses (addressable vs residual, `issue`, `suggested_sharpening`); then the
  convergence ruling — "addressable_votes = K of 3 → REWORK (K≥2) / EXHAUSTED" — taken
  from `_aggregate_votes` / `_converged`. This is the literal debate transcript: three
  independent skeptics on the same challenge set, then the majority verdict.
- **rework round:** rendered by phase_3 when it returns REWORK — the merged sharpenings
  that aren't absorbed yet, i.e. "why we go around again." (The re-run of phase_2 then
  emits the regenerated challenges, so the loop is visible.)
- **phase_4_signals_action_gate:** the premature-end / drift atoms → the computed risk
  levels + `why`, the proposed action, and any veto applied by `signals.py`.
- **phase_5_assemble_render:** final verdict + light (🔴🟡🟢) + `readiness_score_delta`
  + `recommended_next_action` + the one-line `reproducible_judgment`.

### Component 3 — hard requirement (enforcement)

In `albert/graph.py._wrap`, after `fn(state)` returns and before `phase_end`, call
`deliberation.assert_emitted(name)` for the soul phases (phase_0/2/3/4/5). A phase that
produced a dict result but emitted no deliberation block raises
`VisibilityContractError` → the run fails closed. Silent deliberation is impossible.

`deliberation.init(run_dir)` is called in `run_albert.py` next to `progress.init(...)`.

### Component 4 — live delivery

- stderr writes use `flush=True`; the process runs unbuffered (`PYTHONUNBUFFERED=1`
  set by `run_albert.py`, or `py -3 -u`).
- The run is invoked **foreground, no `tee`, no redirect** (R23 / no-tee discipline) so
  the blocks stream to the user's terminal as produced.

## Data flow

```
run_albert.py: progress.init + deliberation.init
  → graph._wrap(phase) :
       emit_phase_start_summary; progress.phase_start
       result = phase(state)                # produces structured output
       phase renders narrative → deliberation.block(...)   # live stderr + file
       deliberation.assert_emitted(phase)   # HARD GATE — raises if silent
       emit_stage_summary; progress.phase_end
  → deliberation.md persisted; transcript already streamed live
```

## Error handling

- Any sink failure in `deliberation.block` → `VisibilityContractError` (fail-closed),
  propagated through `_wrap`'s `except` → `emit_phase_error` + re-raise. Consistent with
  `progress.py`.
- A degraded phase (e.g. all 3 votes fell back) STILL must emit a block — it renders
  "degraded: all votes failed, no rework driven" so the user sees the degradation
  rather than silence. (Aligns with R13 no-degraded-silent-success.)
- `assert_emitted` only fires for phases that returned a normal dict result; a phase
  that raised before emitting is already handled by the existing `phase_error` path.

## Testing

- `tests/test_deliberation.py`:
  - `block` writes to both the file and stderr (capture `capsys`), content present.
  - `block` raises `VisibilityContractError` when the run dir is unwritable.
  - `assert_emitted` raises for a phase with no block, passes after a block.
  - `init` resets the emitted set between runs.
- Per-phase: each soul phase, given a minimal state, emits a non-empty block
  (assert `deliberation.emitted(name)` true and the file contains the phase's marker).
- Graph-level: a stub phase that returns a dict without emitting → the wrapped node
  raises `VisibilityContractError` (silent phase fails closed).

## Files

- Create: `albert/deliberation.py`, `tests/test_deliberation.py`
- Modify: `albert/phases/phase_0_intake_grounding.py`,
  `albert/phases/phase_2_challenge_generation.py`,
  `albert/phases/phase_3_self_critique_audit.py`,
  `albert/phases/phase_4_signals_action_gate.py`,
  `albert/phases/phase_5_assemble_render.py`,
  `albert/graph.py` (init wiring note + `assert_emitted` in `_wrap`),
  `run_albert.py` (`deliberation.init` + unbuffered stdout/stderr),
  `SKILL.md` (document the always-on deliberation stream + foreground-run convention).
