# Albert Refuse-Redirected-Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standalone Albert refuses to run (exit 2) when its output isn't on a live terminal, so colleagues can't hide the deliberation via `| tee`, `> file`, `2>&1 |`, or backgrounding.

**Architecture:** A pure testable predicate `_redirect_refusal(...)` in `run_albert.py` returns a refusal message unless cockpit / `--allow-redirect` / `--dry-run` / all-streams-TTY. `main()` calls it early and exits 2 on refusal. New `--allow-redirect` flag + `ALBERT_ALLOW_REDIRECT` env escape. SKILL.md states the hard rule.

**Tech Stack:** Python 3, pytest.

---

## Reference (current code)

`run_albert.py` `main()` after the UTF-8 setup parses args:
```python
    ap = argparse.ArgumentParser(prog="run_albert")
    ap.add_argument("proposal", nargs="?")
    ap.add_argument("--input", dest="input_json")
    ap.add_argument("--json-out", action="store_true")
    ap.add_argument("--resume", dest="resume_id")
    ap.add_argument("--gc", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--user-email")
    args = ap.parse_args()
    if args.gc:
        _gc(); return 0
    if not args.proposal and not args.input_json and not args.resume_id:
        ap.error("a proposal, --input, or --resume is required")
    run_id = args.resume_id or f"run-{int(time.time())}-{uuid.uuid4().hex[:8]}"
```
`import os`, `sys` already present. Module-level helpers `_apply_standalone_rework_default`, `_force_utf8_console`, `_deliberation_banner` already exist.

---

## Task 1: Refusal predicate + flag + wiring

**Files:**
- Modify: `run_albert.py`
- Test: `tests/test_redirect_refusal.py`

- [ ] **Step 1: Write the failing test** `tests/test_redirect_refusal.py`:

```python
import importlib
run_albert = importlib.import_module("run_albert")


class _FakeStream:
    def __init__(self, isatty_value):
        self._tty = isatty_value

    def isatty(self):
        return self._tty


class _NoIsatty:
    pass


def _tty_pair():
    return (_FakeStream(True), _FakeStream(True))


def test_allowed_when_interactive():
    assert run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=False, dry_run=False, streams=_tty_pair()) is None


def test_refused_when_a_stream_not_tty():
    msg = run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=False, dry_run=False,
        streams=(_FakeStream(True), _FakeStream(False)))
    assert msg is not None
    assert "拒絕執行" in msg
    assert "--allow-redirect" in msg


def test_cockpit_exempt():
    assert run_albert._redirect_refusal(
        is_cockpit=True, allow_redirect=False, dry_run=False,
        streams=(_FakeStream(False), _FakeStream(False))) is None


def test_allow_redirect_exempt():
    assert run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=True, dry_run=False,
        streams=(_FakeStream(False), _FakeStream(False))) is None


def test_dry_run_exempt():
    assert run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=False, dry_run=True,
        streams=(_FakeStream(False), _FakeStream(False))) is None


def test_stream_without_isatty_treated_as_not_tty():
    msg = run_albert._redirect_refusal(
        is_cockpit=False, allow_redirect=False, dry_run=False,
        streams=(_NoIsatty(),))
    assert msg is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_redirect_refusal.py -v`
Expected: FAIL (`_redirect_refusal` not defined).

- [ ] **Step 3: Add the helpers** to `run_albert.py` (module level, after `_deliberation_banner`):

```python
def _isatty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


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

- [ ] **Step 4: Add the flag** — in the argparse block, after the `--dry-run` line:

```python
    ap.add_argument("--allow-redirect", action="store_true")
```

- [ ] **Step 5: Wire the check** — immediately AFTER the existing arg-validation line
`if not args.proposal and not args.input_json and not args.resume_id: ap.error(...)`
and BEFORE `run_id = ...`, add:

```python
    is_cockpit = bool(args.input_json or args.json_out)
    allow_redirect = bool(args.allow_redirect) or os.environ.get("ALBERT_ALLOW_REDIRECT") == "1"
    _refusal = _redirect_refusal(is_cockpit=is_cockpit, allow_redirect=allow_redirect,
                                 dry_run=args.dry_run, streams=(sys.stdout, sys.stderr))
    if _refusal:
        sys.stderr.write(_refusal + "\n")
        return 2
```

- [ ] **Step 6: Run tests**

Run: `py -3 -m pytest tests/test_redirect_refusal.py -v`
Expected: PASS (6 passed).

- [ ] **Step 7: Full suite + smoke**

Run: `py -3 -m pytest -q` (expect green, was 169 → 175) and `py -3 run_albert.py --help` (loads, shows `--allow-redirect`).

Also confirm the gate fires when piped (non-TTY) but `--help` still works:
Run: `py -3 run_albert.py "x" --dry-run | cat` → should NOT refuse (dry-run exempt) — prints the dry-run line.
Run: `echo "" | py -3 run_albert.py "x"` (stdin piped; stdout is a pipe to nothing interactive) — in a non-TTY harness this should print the refusal and exit 2. (If the harness stdout is already non-TTY, a plain `py -3 run_albert.py "x"` will also refuse — that is correct behavior; use `--allow-redirect` to run it there.)

- [ ] **Step 8: Commit**

```bash
git -c commit.gpgsign=false add run_albert.py tests/test_redirect_refusal.py
git -c commit.gpgsign=false commit -m "feat(cli): refuse standalone run when output is redirected (force live deliberation; --allow-redirect escape)"
```

---

## Task 2: SKILL.md — state the hard rule

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Replace** the soft sentence in the "看辯論過程(同事用)" section. Change:

```
想看即時就**不要** `| tee`、`> file`
或丟背景跑;那些會把即時畫面導走(完整內容仍在 deliberation.md)。
```

to:

```
**強制規定:** standalone 模式必須在互動終端機跑。若偵測到輸出被導走(`| tee`、`> 檔案`、
`2>&1 |`、丟背景),Albert 會**直接拒絕執行**並提示你正確跑法 —— 確保辯論一定看得到。
真的要非互動執行(CI / 自動化)才加 `--allow-redirect`;cockpit 模式(`--input`/`--json-out`)
自動豁免。完整內容仍會存到 `runs/<id>/deliberation.md`。
```

- [ ] **Step 2: Commit**

```bash
git -c commit.gpgsign=false add SKILL.md
git -c commit.gpgsign=false commit -m "docs: hard rule — standalone refuses redirected output"
```

---

## Self-Review

**1. Spec coverage:**
- `_redirect_refusal` predicate with cockpit/allow_redirect/dry_run/all-TTY exemptions → Task 1 Step 3. ✓
- `_isatty` fail-safe (missing isatty → not tty) → Task 1 Step 3 + test `test_stream_without_isatty...`. ✓
- `--allow-redirect` flag + `ALBERT_ALLOW_REDIRECT` env → Task 1 Step 4/5. ✓
- early wiring, return 2 → Task 1 Step 5. ✓
- SKILL.md hard rule → Task 2. ✓
- tests (allow/refuse/cockpit/allow_redirect/dry_run/no-isatty) → Task 1 Step 1. ✓

**2. Placeholder scan:** none — code complete; Step 7's harness note is an explicit observation about TTY behavior, not a TODO.

**3. Type consistency:** `_redirect_refusal(*, is_cockpit, allow_redirect, dry_run, streams)` and `_isatty(stream)` defined and called with matching keyword args; flag `args.allow_redirect`; returns `str|None` used as truthy. ✓
