# Albert — Refuse Redirected Output (force live deliberation) — Design

**Date:** 2026-06-03
**Status:** approved (directive 2026-06-03: 強制禁止 tee / redirect / background — the skill must refuse, not just warn)

## Problem

The deliberation cards stream live to the terminal, but a colleague can still *hide* them by
piping/redirecting/backgrounding (`| tee`, `> file`, `2>&1 | …`, `nohup … &`). A polite SKILL.md
note ("don't do that") does not stop it. The user wants the **skill itself to refuse to run**
when its live deliberation would not be visible.

## Goal

In **standalone** mode, if the process's output is not attached to a live interactive terminal,
Albert **refuses to run** (exits non-zero) with a clear message telling the colleague to run it
directly in a terminal. Genuine non-interactive use stays possible via an explicit escape.

## Non-goals (YAGNI)

- Not blocking **cockpit** mode (`--input` / `--json-out`) — it is designed to be invoked
  programmatically and its output captured. It is exempt.
- Not blocking `--dry-run` (produces no deliberation) or `--gc`.
- Not detecting every conceivable hiding trick — TTY detection covers the real cases
  (pipe, file redirect, background-to-file, CI). The full transcript is always still in
  `deliberation.md`.

## Design (`run_albert.py` + `SKILL.md`)

### Refusal predicate (pure, testable)

```python
def _redirect_refusal(*, is_cockpit, allow_redirect, dry_run, streams):
    """Return a refusal message if a standalone run's live deliberation would be hidden
    (output not on an interactive terminal), else None. Cockpit / --allow-redirect /
    --dry-run are exempt; otherwise ALL streams must be TTYs."""
    if is_cockpit or allow_redirect or dry_run:
        return None
    if all(_isatty(s) for s in streams):
        return None
    return (
        "Albert 拒絕執行:辯論過程必須即時顯示在終端機,但偵測到輸出被導走"
        "(pipe / > 檔案 / 2>&1 | tee / 背景執行)。\n"
        "請直接在終端機跑:  py -3 run_albert.py \"<你的提案>\"\n"
        "(別加 | tee、> 檔案、2>&1 |、或丟背景。完整存檔仍會在 runs/<id>/deliberation.md。)\n"
        "若確實需要非互動執行,加 --allow-redirect。"
    )
```

`_isatty(s)` is a tiny guard: `try: return bool(s.isatty()) except Exception: return False`
(a stream without `isatty` counts as not-a-tty → refuse, the safe default).

### Wiring in `main()`

After `argparse` and the early `--gc` / arg-validation returns, before creating the run dir:

```python
    is_cockpit = bool(args.input_json or args.json_out)
    allow_redirect = bool(args.allow_redirect) or os.environ.get("ALBERT_ALLOW_REDIRECT") == "1"
    _refusal = _redirect_refusal(is_cockpit=is_cockpit, allow_redirect=allow_redirect,
                                 dry_run=args.dry_run, streams=(sys.stdout, sys.stderr))
    if _refusal:
        sys.stderr.write(_refusal + "\n")
        return 2
```

New CLI flag: `ap.add_argument("--allow-redirect", action="store_true")`.

Note: `_force_utf8_console` still runs first (so even the refusal message renders cleanly).
The refusal happens before any run work, so no run dir / LLM calls are wasted.

## Error handling

- `_isatty` swallows any exception and treats the stream as not-a-tty (fail-safe toward
  refusing — better to refuse than silently hide).
- The refusal is a normal `return 2`; no exception.

## Testing (`tests/test_redirect_refusal.py`)

- standalone + both streams TTY → `None` (allowed).
- standalone + one stream not TTY → message containing "拒絕執行" and "--allow-redirect".
- `is_cockpit=True` + non-TTY streams → `None`.
- `allow_redirect=True` + non-TTY streams → `None`.
- `dry_run=True` + non-TTY streams → `None`.
- a stream object without `isatty` → treated as non-TTY → refuse (standalone).

Use a `_FakeStream(isatty_value)` with an `isatty()` method.

Full suite stays green; `py -3 run_albert.py --help` still loads.

## Files

- Modify: `run_albert.py` (helper + `--allow-redirect` flag + wiring), `SKILL.md` (hard rule).
- Test: `tests/test_redirect_refusal.py`.
- Unchanged: deliberation/graph/schemas/contract.
