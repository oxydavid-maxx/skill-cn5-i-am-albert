# Albert — Colleague-Proof Live Deliberation On Screen — Design

**Date:** 2026-06-03
**Status:** approved (directive 2026-06-03: colleagues must see the deliberation live on screen)

## Problem

The deliberation cards already stream to `stderr` (flushed) and are saved to
`runs/<id>/deliberation.md`. But the skill is being distributed to colleagues, and a colleague
running it on their own machine is NOT guaranteed to see the debate live:

- **Encoding (the real blocker):** `run_albert.py` startup calls
  `sys.stdout/stderr.reconfigure(line_buffering=True)` but does NOT set `encoding`. On Windows
  (default cp950) the 繁體中文 cards render as **mojibake**, and an unencodable char can raise
  `UnicodeEncodeError` inside `deliberation.block`'s stderr write → caught as
  `VisibilityContractError` → the run **fails** for the colleague. The maintainer only ever saw
  clean cards because they manually exported `PYTHONUTF8=1 PYTHONIOENCODING=utf-8`; a colleague
  won't know to.
- **Discoverability:** nothing on screen tells the colleague "the debate is streaming below" or
  where the saved copy is.

An agent-side behavior rule ("don't background it") cannot help a colleague who runs it
themselves. The guarantee must live in the skill.

## Goal

Any colleague, any machine, **no environment setup**: run `py -3 run_albert.py "<提案>"` in a
terminal → the deliberation cards appear **clean (no mojibake) and live** on screen, and the run
never crashes on an encoding error.

## Non-goals (YAGNI)

- Not forcing visibility when a colleague *deliberately* redirects/backgrounds/pipes output —
  that is their explicit choice; the skill guarantees the normal foreground-terminal case and
  always leaves the full transcript in `deliberation.md`.
- No change to what the cards contain or to the `assert_emitted` contract.
- Not moving cards from stderr to stdout (stderr keeps stdout clean for the cockpit `--json-out`
  path; stderr still displays on screen in a terminal).

## Design (all in `run_albert.py` + `SKILL.md`)

### 1. Force a UTF-8 console (the fix)

Replace the current startup block with a testable helper:

```python
def _force_utf8_console(streams):
    """Make CJK deliberation cards render cleanly + live on any machine, no env setup.
    errors='replace' so a console that can't encode a glyph degrades it to '?' rather
    than raising UnicodeEncodeError (which would fail the visibility contract)."""
    for s in streams:
        try:
            s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass
```

`main()` calls `os.environ.setdefault("PYTHONUNBUFFERED", "1")` then
`_force_utf8_console((sys.stdout, sys.stderr))` as the first thing.

### 2. On-screen "live debate" banner at run start

```python
def _deliberation_banner(run_dir) -> str:
    return ("\n▼▼▼ 辯論過程(即時顯示)▼▼▼\n"
            f"（完整存檔:{Path(run_dir) / 'deliberation.md'}）\n")
```

`main()` writes it to `sys.stderr` (next to the card stream) right after
`deliberation.init(run_dir)`, so the colleague sees the framing immediately above the cards.

### 3. End-of-run pointer

On successful completion, print to stdout a prominent line with the report path and the
deliberation.md path, so the colleague always knows where the saved debate + report are even if
they looked away.

### 4. SKILL.md

Add a short "看辯論過程" note: colleagues just run `py -3 run_albert.py "<提案>"` in a terminal;
the debate streams live (UTF-8, no setup needed); a full copy is saved to
`runs/<id>/deliberation.md`; don't pipe/background it if you want to watch live.

## Error handling

- `_force_utf8_console` swallows per-stream reconfigure failures (older/odd streams) — best
  effort; `errors="replace"` guarantees no encode crash even if reconfigure partially fails.
- Banner/pointer writes are plain prints; a failure there must not abort the run (wrap if needed).

## Testing

- `_force_utf8_console`: a fake stream object records `reconfigure(**kwargs)`; assert it is called
  with `encoding="utf-8"`, `errors="replace"`, `line_buffering=True`; a stream whose
  `reconfigure` raises does not propagate.
- `_deliberation_banner(run_dir)`: returned string contains `辯論過程` and the
  `deliberation.md` path under run_dir.
- Full suite stays green; `py -3 run_albert.py --help` still loads.

## Files

- Modify: `run_albert.py` (helpers + call sites), `SKILL.md` (colleague note).
- Test: `tests/test_console_utf8.py`.
- Unchanged: `albert/deliberation.py`, graph, schemas, contract.
