# Albert Flash Mode (one Opus call, bypass all flow) — Design

**Date:** 2026-06-03
**Status:** approved (directive 2026-06-03: add flash mode — call Opus once, bypass all flow)

## Goal

A 4th profile **`flash`**: a single Opus call that audits the proposal and emits the full
contract, **bypassing research (phase_0) and the entire multi-phase debate (p2/p3/p4)**. Fastest
possible (~1-2 min, one call, no web search). Lowest quality by design — Albert's one-shot gut
judgment with no external grounding and no exhaustion debate.

## Profiles after this change

`thorough` (default, full debate) · `--fast` (research-preserving, ~parity) · `--quick`
(minimal research + one combined call, ~80%) · **`--flash` (no research, one call, fastest)**.

## Design

### Selection / precedence

- `albert/profile.py`: add `flash` + `FLASH_DEFAULTS = {"ALBERT_MAX_REWORK": "0"}` (research
  knobs are irrelevant — flash skips research; keep it minimal). `resolve_profile` already
  lowercases env so `ALBERT_PROFILE=flash` resolves.
- `run_albert.py`: add `--flash`. Precedence when multiple given: **flash > quick > fast**
  (most-aggressive wins), with a one-line stderr note. `profile` goes into the initial state
  (already wired; `profile` is declared in `AlbertState`).

### Graph: conditional START

Currently `g.add_edge(START, "phase_0_intake_grounding")`. Replace with a conditional so flash
bypasses p0:

```python
def _route_from_start(state):
    return "phase_flash" if state.get("profile") == "flash" else "phase_0_intake_grounding"
```

`g.add_conditional_edges(START, _route_from_start, {"phase_flash": "phase_flash",
"phase_0_intake_grounding": "phase_0_intake_grounding"})` + `g.add_edge("phase_flash",
"phase_5_assemble_render")`. The existing `_route_after_intake` (after p0, for quick) stays. All
other edges unchanged.

### Shared core: `combined_audit` (DRY quick + flash)

Extract the one-call body of `phase_quick_combined` into a reusable function so flash reuses it:

```python
# in albert/phases/_combined.py (new)
def combined_audit(state, *, prompt, node, banner, research_text) -> dict:
    """ONE call_claude(QUICK_COMBINED) + apply_signals + contract fields + deliberation block.
    Shared by phase_quick_combined (with research) and phase_flash (no research)."""
```

It does exactly what `phase_quick_combined` does today, except:
- the research line in `ctx` is built from the passed `research_text` (empty string for flash → no
  Research section),
- the prompt file name is `prompt`,
- the deliberation `block(node, ...)` uses the passed `node` + `banner`,
- the `assert_emitted` node name is `node`.

`phase_quick_combined(state)` becomes a thin wrapper:
`return combined_audit(state, prompt="quick_combined", node="phase_quick_combined",
banner="PHASE Q ─ 快速審查(quick)", research_text=research_refs(state.get("research", [])))`.
The existing quick tests (`tests/test_phase_quick_combined.py`) verify the refactor is behavior-preserving.

### `phase_flash`

```python
# albert/phases/phase_flash.py
def phase_flash(state):
    inp = state.get("albert_input") or {}
    state.setdefault("current_answer", inp.get("current_answer", ""))
    state["output_purpose"] = state.get("output_purpose") or inp.get("output_purpose", "")
    state["proposal"] = state.get("proposal") or inp.get("proposal", {}) or {}
    state["research"] = []
    return combined_audit(state, prompt="flash_combined", node="phase_flash",
                          banner="PHASE F ─ 閃電審查(flash)", research_text="")
```

(phase_0 is skipped for flash, so flash copies the few fields render/email/the call need straight
from `albert_input` — no LLM, no research.)

### Prompt `flash_combined.txt`

Same shape as `quick_combined.txt` but states there is **no external research**: "You have NO
external research — give Albert's best ONE-SHOT judgment from the proposal alone. Be decisive;
flag what you'd want to verify as missing_evidence / recommended_next_probe." Reuses
`QUICK_COMBINED` schema. 繁體中文 directive.

### Contract / degraded

`combined_audit` sets the same fields `phase_quick_combined` does today (albert_challenges,
top_ambiguities, weak_points, would_survive_leadership, apply_signals → risk/action/verdict,
verdict="exhausted", phase_2_status + phase_4_status + phase_4_complete). So `render.build_challenge`,
p5, and the cockpit contract all work unchanged. Degraded detection works (flash sets the status
keys in `_STATUS_KEYS`).

## Honest quality

Lowest of the four — no research grounding, no multi-vote debate, one pass. It's "Albert's gut
take in one Opus call." Good for an instant sanity read; use quick/fast/thorough for anything
real. The flash prompt pushes the model to surface what it would verify (so gaps are visible
rather than hidden).

## Testing

- `profile`: `resolve_profile`/`apply_profile` handle "flash"; FLASH_DEFAULTS sets MAX_REWORK=0.
- `run_albert`: `--flash` → profile "flash"; precedence flash>quick>fast; `--flash --dry-run
  --allow-redirect` prints `[profile] flash`.
- graph: `_route_from_start({"profile":"flash"})=="phase_flash"`, else "phase_0_intake_grounding";
  a graph-through-state-filter regression test (like quick's) that flash routes to phase_flash;
  build_graph compiles with the flash node.
- `combined_audit` / `phase_quick_combined`: existing quick tests stay green after the refactor.
- `phase_flash` (LLM stubbed): populates the contract, sets current_answer from albert_input,
  research==[], emits a `phase_flash` deliberation block with the PHASE F banner (and NOT phase_0
  research); degraded stub path on failure.
- Full suite green; cockpit contract test green.
- Smoke/benchmark: one real `--flash` run → wall-clock (~1-2 min) into `docs/speedup-results.md`.

## Files

- Create: `albert/phases/_combined.py` (or put `combined_audit` in phase_quick_combined and import),
  `albert/phases/phase_flash.py`, `albert/prompts/flash_combined.txt`, tests.
- Modify: `albert/profile.py` (FLASH_DEFAULTS), `run_albert.py` (--flash + precedence),
  `albert/graph.py` (conditional START + flash node), `albert/phases/phase_quick_combined.py`
  (thin wrapper over combined_audit), `SKILL.md`, `docs/speedup-results.md`.
- Unchanged: schemas (reuse QUICK_COMBINED), cockpit contract, deliberation/redirect-refusal, models.
