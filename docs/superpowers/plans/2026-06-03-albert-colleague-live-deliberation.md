# Albert Colleague-Proof Live Deliberation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any colleague, any machine, no env setup → `py -3 run_albert.py "<提案>"` in a terminal shows the 繁中 deliberation cards clean (no mojibake) and live, without crashing on encoding.

**Architecture:** `run_albert.py` forces a UTF-8 + line-buffered console at startup (testable helper), prints an on-screen "live debate" banner at run start and a paths pointer at the end; SKILL.md documents it. No changes to the card content or the assert_emitted contract.

**Tech Stack:** Python 3, pytest.

---

## Reference (current code)

`run_albert.py` `main()` currently starts with:
```python
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
```
It later calls `deliberation.init(run_dir)` (≈ line 47). On success it prints a one-line summary near the end of `main()` (a `sys.stderr.write(... standalone=...)` or `print`). `import os`, `sys`, `from pathlib import Path` are already present at the top.

---

## Task 1: UTF-8 console + on-screen banner + end pointer

**Files:**
- Modify: `run_albert.py`
- Test: `tests/test_console_utf8.py`

- [ ] **Step 1: Write the failing test** `tests/test_console_utf8.py`:

```python
import importlib
run_albert = importlib.import_module("run_albert")


class _FakeStream:
    def __init__(self, raise_on_reconfigure=False):
        self.calls = []
        self._raise = raise_on_reconfigure

    def reconfigure(self, **kwargs):
        if self._raise:
            raise ValueError("cannot reconfigure")
        self.calls.append(kwargs)


def test_force_utf8_console_sets_utf8_replace_linebuffered():
    s = _FakeStream()
    run_albert._force_utf8_console([s])
    assert s.calls == [{"encoding": "utf-8", "errors": "replace", "line_buffering": True}]


def test_force_utf8_console_swallows_reconfigure_error():
    s = _FakeStream(raise_on_reconfigure=True)
    run_albert._force_utf8_console([s])  # must not raise
    assert s.calls == []


def test_deliberation_banner_contains_label_and_path(tmp_path):
    out = run_albert._deliberation_banner(tmp_path)
    assert "辯論過程" in out
    assert "deliberation.md" in out
    assert str(tmp_path) in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_console_utf8.py -v`
Expected: FAIL (`_force_utf8_console` / `_deliberation_banner` not defined).

- [ ] **Step 3: Add the helpers** to `run_albert.py` at module level (after the existing `_apply_standalone_rework_default` helper):

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


def _deliberation_banner(run_dir) -> str:
    return ("\n▼▼▼ 辯論過程(即時顯示)▼▼▼\n"
            f"（完整存檔:{Path(run_dir) / 'deliberation.md'}）\n")
```

- [ ] **Step 4: Replace the startup block** in `main()`. Change:
```python
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
```
to:
```python
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    _force_utf8_console((sys.stdout, sys.stderr))
```

- [ ] **Step 5: Emit the banner** at run start. Find `deliberation.init(run_dir)` in `main()` and add immediately after it:
```python
        sys.stderr.write(_deliberation_banner(run_dir))
        sys.stderr.flush()
```
(Match the indentation of the surrounding code at that point.)

- [ ] **Step 6: End pointer.** Find the success summary near the end of `main()` (the line that prints `standalone=...`/verdict after `final = graph.invoke(...)`). Immediately after that existing print, add a prominent paths pointer:
```python
            print(f"\n📄 報告:{final.get('report_path', run_dir / 'albert_review.md')}")
            print(f"💬 辯論全文:{run_dir / 'deliberation.md'}")
```
NOTE for implementer: read the end of `main()` and place these two prints on the SUCCESS path (after the verdict summary, before `return 0`), matching indentation. If `final` isn't in scope there, use `run_dir / 'albert_review.md'` directly. Do not add them on the `Run incomplete` (return 2) path.

- [ ] **Step 7: Run tests**

Run: `py -3 -m pytest tests/test_console_utf8.py -v`
Expected: PASS (3 passed).

- [ ] **Step 8: Full suite + smoke**

Run: `py -3 -m pytest -q` (expect green, was 166) and `py -3 run_albert.py --help` (loads cleanly).

- [ ] **Step 9: Commit**

```bash
git -c commit.gpgsign=false add run_albert.py tests/test_console_utf8.py
git -c commit.gpgsign=false commit -m "feat(cli): force UTF-8 console + live-debate banner so colleagues see deliberation on screen"
```

---

## Task 2: Document it in SKILL.md

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Add a section** after the "Deliberation stream (always on)" section:

```markdown
## 看辯論過程(同事用)

在終端機直接跑就會**即時**看到辯論卡片(研究 → 拷問 → 三票辯論 → 重做 → 裁決):

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py "<你的提案>"

不需要任何環境設定 — 程式會自動用 UTF-8 顯示(Windows 也不會亂碼)。每張卡片同時存到
`runs/<run_id>/deliberation.md`(跑完螢幕也會印出路徑)。想看即時就**不要** `| tee`、`> file`
或丟背景跑;那些會把即時畫面導走(完整內容仍在 deliberation.md)。
```

- [ ] **Step 2: Commit**

```bash
git -c commit.gpgsign=false add SKILL.md
git -c commit.gpgsign=false commit -m "docs: how colleagues watch the live deliberation (UTF-8, no setup)"
```

---

## Self-Review

**1. Spec coverage:**
- UTF-8 + errors=replace + line_buffering helper → Task 1 Step 3/4. ✓
- on-screen banner at start → Task 1 Step 3/5. ✓
- end-of-run paths pointer → Task 1 Step 6. ✓
- SKILL.md colleague note → Task 2. ✓
- tests (reconfigure kwargs, swallow error, banner content) → Task 1 Step 1. ✓

**2. Placeholder scan:** none — code blocks complete; the Step-6 NOTE is an explicit placement instruction with a concrete fallback (`run_dir / 'albert_review.md'`), not a TODO.

**3. Type consistency:** `_force_utf8_console(streams)` and `_deliberation_banner(run_dir)` defined and called with matching signatures; `Path` already imported; banner returns a str used by `sys.stderr.write`. ✓
