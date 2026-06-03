# Albert Fast Mode (research-preserving) — Design

**Date:** 2026-06-03
**Status:** approved (directive 2026-06-03: add a fast mode — half time, ~90% quality — alongside the current mode; lever choice = 保研究型)

## Problem / Goal

Albert's thorough run is 9-15 min. Users want a **fast mode** for quick interactive use:
target **≈ half the wall-clock at ~90% of the quality**, while the **current ("thorough") mode
stays the default**. Per the lever decision, fast mode is **research-preserving**: it keeps full
research breadth and earns speed elsewhere.

## What "fast" trades (lever decision = research-preserving)

Speed levers used (no loss of research breadth):
- **No rework loop** (`ALBERT_MAX_REWORK=0`) — removes the dominant time variance (a full
  challenge+critique re-run). The self-critique 3-vote debate STILL runs once (visible); it just
  doesn't drive a regeneration pass.
- **Faster web search** (`ALBERT_WEBSEARCH_MAX_TURNS=3`, down from 5) — each search resolves in
  fewer agent turns. Floor is 3 (turns=2 was shown to break the search tool cycle).
- **Wider research parallelism** (`ALBERT_RESEARCH_WIDTH=5`, up from the current 3-wide cap) —
  the 5 wave-1 queries run concurrently in one batch instead of 3+2, cutting phase-0 wall-clock
  WITHOUT dropping any query. Capped at 5 (6-8 wide previously caused init-timeout / rate-limit
  retry storms).
- **Opportunistic fast search backend** — if `ALBERT_SEARCH_BACKEND` (+ key) is set, fast mode
  uses it (already wired); this alone takes fast well under half.

Explicitly NOT changed in fast mode (these protect the 90% quality floor):
- Research breadth: still up to 5 queries (preserved).
- Self-critique: still 3 independent votes (avoids the self-critique paradox).
- Models: strong roles stay on Opus (Sonnet was benchmarked slower on this OAuth + shallower).
- Deliberation visibility, hard `assert_emitted`, and the redirect-refusal gate are unchanged.

## Honest expectation

Guaranteed savings = no-rework + faster/wider search. This reaches ≈half **when** the thorough
baseline would have spent a rework cycle, OR when a search backend key is present. With neither,
expect ~0.6× (still meaningfully faster). The plan's A/B benchmark measures the real ratio on a
fixed proposal; if it lands materially above target, we revisit the lever set (a follow-up could
add a `--faster` that also trims research — out of scope here).

## Design

### Selection

- New CLI flag `--fast` and env `ALBERT_PROFILE` (`thorough` | `fast`). Default = `thorough`
  (current behavior, unchanged). `--fast` ⇒ profile `fast`.
- Cockpit mode (`--input`/`--json-out`) may also pass `--fast`; the profile is mode-independent.

### `albert/profile.py` (new, thin, pure-ish)

```python
FAST_DEFAULTS = {
    "ALBERT_MAX_REWORK": "0",
    "ALBERT_WEBSEARCH_MAX_TURNS": "3",
    "ALBERT_RESEARCH_WIDTH": "5",
}

def resolve_profile(args_fast: bool, env) -> str:
    if args_fast:
        return "fast"
    return (env.get("ALBERT_PROFILE") or "thorough").strip().lower()

def apply_profile(profile: str, env) -> dict:
    """Set fast-mode knob DEFAULTS into env. Explicit pre-set env always wins
    (we only setdefault). Returns the dict of values actually applied (for logging)."""
    applied = {}
    if profile == "fast":
        for k, v in FAST_DEFAULTS.items():
            if k not in env:
                env[k] = v
                applied[k] = v
    return applied
```

`run_albert.main()` after arg-parse (and after the standalone-rework default, which must NOT
override fast's `MAX_REWORK=0`): `profile = resolve_profile(args.fast, os.environ)` then
`apply_profile(profile, os.environ)`. Ordering: `apply_profile` runs BEFORE
`_apply_standalone_rework_default` so that in fast mode `ALBERT_MAX_REWORK` is already set to "0"
and the standalone helper (which only setdefaults to "1") leaves it. Print a one-line
`[profile] fast — MAX_REWORK=0, WEBSEARCH_MAX_TURNS=3, RESEARCH_WIDTH=5` to stderr so the user
sees which mode ran.

### Phase-0 research width knob

`phase_0_intake_grounding` currently does `parallel_map(websearch, queries[:5], max_workers=3)`
(the wave-1 line). Change the width to read a knob:

```python
def _research_width() -> int:
    try:
        return max(1, int(os.environ.get("ALBERT_RESEARCH_WIDTH", "3")))
    except (TypeError, ValueError):
        return 3
```

and use `parallel_map(websearch, queries[:5], max_workers=_research_width())`. Default 3
(thorough, unchanged behavior); fast sets 5. The `[:5]` query slice is unchanged (breadth kept).

### Deliberation banner

Add the active profile to the run-start banner (already emitted): show `模式:fast` / `模式:
thorough` so colleagues watching the stream know which ran.

## Error handling

- `_research_width` falls back to 3 on bad env (same pattern as `_max_rework`).
- `apply_profile` only setdefaults — never clobbers an explicit env value; unknown profile names
  are treated as thorough (no-op).

## Testing

- `resolve_profile`: `--fast` → "fast"; no flag + `ALBERT_PROFILE=fast` → "fast"; neither →
  "thorough"; bad case-insensitivity handled.
- `apply_profile`: profile "fast" on empty env sets the 3 FAST_DEFAULTS; pre-set
  `ALBERT_MAX_REWORK=2` is preserved (not clobbered); profile "thorough" sets nothing.
- Ordering: simulate run_albert's sequence (apply_profile fast → then
  `_apply_standalone_rework_default("standalone", env)`) → `ALBERT_MAX_REWORK == "0"` (fast wins).
- `_research_width`: default 3; env "5" → 5; bad value → 3.
- `run_albert --help` shows `--fast`; full suite green.
- **Benchmark (separate plan task, run once, not a unit test):** A/B the SAME proposal in
  thorough vs fast; record wall-clock ratio + a quality comparison into
  `docs/speedup-results.md` (fast section): verdict/light parity, # challenges, competitors named,
  ambiguities caught, soul-grade checklist. Target: ratio ≤ ~0.55 and quality ≥ 90%.

## Files

- Create: `albert/profile.py`, `tests/test_profile.py`.
- Modify: `run_albert.py` (`--fast` flag + resolve/apply + banner profile line),
  `albert/phases/phase_0_intake_grounding.py` (`_research_width`),
  `SKILL.md` (document `--fast`), `docs/speedup-results.md` (fast-mode A/B results — at execution).
- Unchanged: graph, schemas, cockpit contract, deliberation/redirect-refusal, models routing.
