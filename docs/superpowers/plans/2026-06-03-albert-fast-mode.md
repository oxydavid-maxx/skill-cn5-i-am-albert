# Albert Fast Mode (research-preserving) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--fast` profile (research-preserving: no rework, faster + wider search) alongside the unchanged default "thorough" mode, targeting ≈half wall-clock at ~90% quality, verified by an A/B benchmark.

**Architecture:** A thin `albert/profile.py` flips EXISTING knobs (`ALBERT_MAX_REWORK`, `ALBERT_WEBSEARCH_MAX_TURNS`, `ALBERT_RESEARCH_WIDTH`) as fast defaults (setdefault — explicit env wins); `run_albert.py` resolves the profile from `--fast`/`ALBERT_PROFILE` and applies it before the standalone-rework default; `phase_0` reads a new `ALBERT_RESEARCH_WIDTH` knob for parallel search width. No graph/schema/contract changes.

**Tech Stack:** Python 3, pytest.

---

## Reference (current code)

- `run_albert.py` `main()` order: `_force_utf8_console(...)` → argparse → `--gc` early return → arg validation `ap.error(...)` → **redirect-refusal gate** (`_redirect_refusal`, returns 2) → `run_id`/`run_dir` → `deliberation.init` + banner → SqliteSaver/build_graph → `ai = build_input(...)` → `_apply_standalone_rework_default(ai["mode"], os.environ)` → `graph.invoke`. `import os, sys` present.
- `_apply_standalone_rework_default(mode, env)` does `env.setdefault`-style: `if mode=="standalone" and "ALBERT_MAX_REWORK" not in env: env["ALBERT_MAX_REWORK"]="1"`.
- `albert/graph.py:_max_rework()` reads `os.environ["ALBERT_MAX_REWORK"]` (default "2").
- `albert/phases/phase_0_intake_grounding.py` wave-1 line: `wave1 = parallel_map(websearch, (plan.get("queries") or [])[:5])` — NOTE: confirm whether it currently passes `max_workers=3`; if a `max_workers=` arg is present, replace its value with `_research_width()`; if absent, add `max_workers=_research_width()`. `import os` — confirm present at top of phase_0; add if missing.
- `albert/sdk_client.py:_websearch_max_turns()` reads `ALBERT_WEBSEARCH_MAX_TURNS` (default "5"). (No change — fast just sets the env.)
- `_deliberation_banner(run_dir)` in run_albert builds the run-start banner string.

---

## Task 1: `albert/profile.py` — profile resolution + knob defaults

**Files:**
- Create: `albert/profile.py`
- Test: `tests/test_profile.py`

- [ ] **Step 1: Write the failing test** `tests/test_profile.py`:

```python
from albert.profile import resolve_profile, apply_profile, FAST_DEFAULTS


def test_resolve_flag_wins():
    assert resolve_profile(True, {}) == "fast"


def test_resolve_env_when_no_flag():
    assert resolve_profile(False, {"ALBERT_PROFILE": "fast"}) == "fast"
    assert resolve_profile(False, {"ALBERT_PROFILE": "FAST"}) == "fast"


def test_resolve_default_thorough():
    assert resolve_profile(False, {}) == "thorough"
    assert resolve_profile(False, {"ALBERT_PROFILE": ""}) == "thorough"


def test_apply_fast_sets_defaults_on_empty_env():
    env = {}
    applied = apply_profile("fast", env)
    assert env["ALBERT_MAX_REWORK"] == "0"
    assert env["ALBERT_WEBSEARCH_MAX_TURNS"] == "3"
    assert env["ALBERT_RESEARCH_WIDTH"] == "5"
    assert applied == dict(FAST_DEFAULTS)


def test_apply_fast_never_clobbers_explicit_env():
    env = {"ALBERT_MAX_REWORK": "2"}
    apply_profile("fast", env)
    assert env["ALBERT_MAX_REWORK"] == "2"      # explicit wins
    assert env["ALBERT_WEBSEARCH_MAX_TURNS"] == "3"  # others still defaulted


def test_apply_thorough_is_noop():
    env = {}
    assert apply_profile("thorough", env) == {}
    assert env == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_profile.py -v`
Expected: FAIL (no module `albert.profile`).

- [ ] **Step 3: Create `albert/profile.py`:**

```python
"""Run profiles: a thin layer that flips EXISTING speed knobs as a coherent set.

'thorough' (default) = current behavior, no knobs touched.
'fast' (research-preserving) = no rework + faster/wider search; research breadth,
3-vote self-critique, and Opus strong roles are all unchanged.

A profile only setdefaults env knobs — an explicitly pre-set env value always wins.
"""
from __future__ import annotations

FAST_DEFAULTS = {
    "ALBERT_MAX_REWORK": "0",
    "ALBERT_WEBSEARCH_MAX_TURNS": "3",
    "ALBERT_RESEARCH_WIDTH": "5",
}


def resolve_profile(args_fast: bool, env) -> str:
    if args_fast:
        return "fast"
    return (env.get("ALBERT_PROFILE") or "thorough").strip().lower() or "thorough"


def apply_profile(profile: str, env) -> dict:
    """Set fast-mode knob DEFAULTS into env (setdefault semantics). Returns the
    dict of values actually applied (for logging). Unknown/thorough = no-op."""
    applied: dict = {}
    if profile == "fast":
        for k, v in FAST_DEFAULTS.items():
            if k not in env:
                env[k] = v
                applied[k] = v
    return applied
```

- [ ] **Step 4: Run to verify it passes**

Run: `py -3 -m pytest tests/test_profile.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add albert/profile.py tests/test_profile.py
git -c commit.gpgsign=false commit -m "feat(profile): thorough/fast run profiles over existing speed knobs"
```

---

## Task 2: Wire `--fast` into run_albert + ordering + banner line

**Files:**
- Modify: `run_albert.py`
- Test: `tests/test_fast_ordering.py`

- [ ] **Step 1: Write the failing test** `tests/test_fast_ordering.py`:

```python
import importlib
run_albert = importlib.import_module("run_albert")
from albert.profile import apply_profile


def test_fast_then_standalone_default_keeps_zero():
    # run_albert must apply the profile BEFORE the standalone-rework default,
    # so fast's MAX_REWORK=0 is not bumped to 1 by the standalone helper.
    env = {}
    apply_profile("fast", env)
    run_albert._apply_standalone_rework_default("standalone", env)
    assert env["ALBERT_MAX_REWORK"] == "0"


def test_thorough_standalone_still_defaults_one():
    env = {}
    apply_profile("thorough", env)
    run_albert._apply_standalone_rework_default("standalone", env)
    assert env["ALBERT_MAX_REWORK"] == "1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_fast_ordering.py -v`
Expected: PASS for `test_thorough...` but this test file will fail to import only if helpers missing — actually both should PASS once Step 3 wiring exists conceptually; the REAL guard is the ordering in `main()`. If both pass already (because they call the helpers directly), that's fine — they lock the ordering contract. Run and confirm green after Step 3; if `test_fast_then_standalone_default_keeps_zero` ever fails, the ordering in `main()` is wrong.

(Note: these tests exercise the helper-level ordering contract directly, which is what `main()` must preserve. They do not import-run `main()`.)

- [ ] **Step 3: Add the `--fast` flag** in the argparse block (after `--allow-redirect`):

```python
    ap.add_argument("--fast", action="store_true")
```

- [ ] **Step 4: Resolve + apply the profile** in `main()`. Add `from albert.profile import resolve_profile, apply_profile` to the top imports. Then, immediately AFTER `args = ap.parse_args()` and the `--gc` early return, BEFORE the redirect-refusal gate, add:

```python
    profile = resolve_profile(args.fast, os.environ)
    _applied = apply_profile(profile, os.environ)
    if profile == "fast":
        sys.stderr.write(f"[profile] fast — {', '.join(f'{k}={v}' for k, v in _applied.items()) or '(all pre-set)'}\n")
```

This runs before `build_input` / `_apply_standalone_rework_default`, so fast's
`ALBERT_MAX_REWORK=0` is already in env when the standalone helper does its setdefault → it stays 0.

- [ ] **Step 5: Show profile in the deliberation banner.** Find `_deliberation_banner(run_dir)` and change its signature + body to include the profile:

```python
def _deliberation_banner(run_dir, profile="thorough") -> str:
    return ("\n▼▼▼ 辯論過程(即時顯示)▼▼▼\n"
            f"（模式:{profile} · 完整存檔:{Path(run_dir) / 'deliberation.md'}）\n")
```

Update its call site in `main()` to pass the profile: `sys.stderr.write(_deliberation_banner(run_dir, profile))`.
NOTE for implementer: `tests/test_console_utf8.py::test_deliberation_banner_contains_label_and_path` calls `_deliberation_banner(tmp_path)` with one arg — the new `profile="thorough"` default keeps that test passing. Verify it still passes.

- [ ] **Step 6: Run tests**

Run: `py -3 -m pytest tests/test_fast_ordering.py tests/test_console_utf8.py -v`
Expected: PASS (ordering tests + the existing banner test still green with the new default arg).

- [ ] **Step 7: Full suite + smoke**

Run: `py -3 -m pytest -q` (expect green) and `py -3 run_albert.py --help` (shows `--fast`).
Run (fast resolves + applies without starting a run): `py -3 run_albert.py "x" --fast --dry-run --allow-redirect` → prints the `[profile] fast — ...` line and the dry-run "Would invoke" line, exit 0.

- [ ] **Step 8: Commit**

```bash
git -c commit.gpgsign=false add run_albert.py tests/test_fast_ordering.py
git -c commit.gpgsign=false commit -m "feat(cli): --fast profile wiring (applied before standalone-rework default) + banner mode"
```

---

## Task 3: Phase-0 research width knob

**Files:**
- Modify: `albert/phases/phase_0_intake_grounding.py`
- Test: `tests/test_research_width.py`

- [ ] **Step 1: Write the failing test** `tests/test_research_width.py`:

```python
import importlib
p0 = importlib.import_module("albert.phases.phase_0_intake_grounding")


def test_research_width_default(monkeypatch):
    monkeypatch.delenv("ALBERT_RESEARCH_WIDTH", raising=False)
    assert p0._research_width() == 3


def test_research_width_env(monkeypatch):
    monkeypatch.setenv("ALBERT_RESEARCH_WIDTH", "5")
    assert p0._research_width() == 5


def test_research_width_bad_value(monkeypatch):
    monkeypatch.setenv("ALBERT_RESEARCH_WIDTH", "notint")
    assert p0._research_width() == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_research_width.py -v`
Expected: FAIL (`_research_width` not defined).

- [ ] **Step 3: Implement.** In `albert/phases/phase_0_intake_grounding.py` add (module level; ensure `import os` is present at the top — add it if not):

```python
def _research_width() -> int:
    try:
        return max(1, int(os.environ.get("ALBERT_RESEARCH_WIDTH", "3")))
    except (TypeError, ValueError):
        return 3
```

Then in the wave-1 search call, set the worker width from the knob. Read the current line first:
- If it is `wave1 = parallel_map(websearch, (plan.get("queries") or [])[:5], max_workers=3)`,
  change `max_workers=3` → `max_workers=_research_width()`.
- If it is `wave1 = parallel_map(websearch, (plan.get("queries") or [])[:5])` (no max_workers),
  change it to `wave1 = parallel_map(websearch, (plan.get("queries") or [])[:5], max_workers=_research_width())`.
Do NOT change the `[:5]` slice (research breadth stays).

- [ ] **Step 4: Run to verify it passes**

Run: `py -3 -m pytest tests/test_research_width.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Full suite**

Run: `py -3 -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git -c commit.gpgsign=false add albert/phases/phase_0_intake_grounding.py tests/test_research_width.py
git -c commit.gpgsign=false commit -m "feat(phase0): ALBERT_RESEARCH_WIDTH knob (default 3; fast=5) — wider parallel search, same breadth"
```

---

## Task 4: Document `--fast` in SKILL.md

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Add a section** after the "看辯論過程(同事用)" section:

```markdown
## Fast mode(`--fast`)

預設是 thorough(完整)模式。趕時間用 fast:

    py -3 run_albert.py "<你的提案>" --fast

Fast 是**保研究型**:研究廣度不變(一樣 5 條查詢、3 票自我辯論、Opus),
速度來自「不跑 rework 重做 + 搜尋更快更並行」(`ALBERT_MAX_REWORK=0`、
`ALBERT_WEBSEARCH_MAX_TURNS=3`、`ALBERT_RESEARCH_WIDTH=5`)。目標 ≈ 一半時間、~90% 品質。
明確設過的環境變數一律優先(profile 只設預設值)。實測比較見 `docs/speedup-results.md`。
```

- [ ] **Step 2: Commit**

```bash
git -c commit.gpgsign=false add SKILL.md
git -c commit.gpgsign=false commit -m "docs: document --fast (research-preserving) mode"
```

---

## Task 5: A/B benchmark (thorough vs fast) — measure the real ratio

**Files:**
- Modify: `docs/speedup-results.md`
- (Uses a fixed proposal file; no code change.)

- [ ] **Step 1: Pick a fixed proposal.** Use the existing gateway thesis at
`C:/Users/Kuangyu/AppData/Local/Temp/albert_gateway_thesis.txt` if present; else write a 1-paragraph
proposal to `docs/bench-proposal.txt` and use that. Record which file was used.

- [ ] **Step 2: Run THOROUGH (baseline), foreground, watch live (NO tee/redirect):**

Run: `py -3 run_albert.py "<bench proposal path>"`
Capture: wall-clock from `runs/<id>/progress.jsonl` (last `total_elapsed_sec`), and the verdict
fields from `runs/<id>/albert_challenge.json` (verdict, light, readiness_score_delta,
#albert_challenges, #weak_points, competitors named in challenges, top_ambiguities).
NOTE: this is a 9-15 min run — run it as the agent watching live per the deliberation rules.

- [ ] **Step 3: Run FAST on the SAME proposal:**

Run: `py -3 run_albert.py "<same bench proposal path>" --fast`
Capture the same metrics + the `[profile] fast` line.

- [ ] **Step 4: Compute + record.** Append a "## Fast mode A/B (2026-06-03)" section to
`docs/speedup-results.md` with: the two wall-clocks, the **ratio (fast/thorough)**, and a quality
table (verdict/light parity, Δ readiness, #challenges, #competitors named, #ambiguities, and a
short soul-grade judgment of whether fast's challenges held the bar). State plainly whether it met
**ratio ≤ ~0.55 and quality ≥ 90%**; if ratio is materially higher, note the cause (thorough didn't
rework / no search backend) and recommend the follow-up lever (`--faster` that trims research).

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add docs/speedup-results.md
git -c commit.gpgsign=false commit -m "docs(bench): fast vs thorough A/B — wall-clock ratio + quality"
```

---

## Self-Review

**1. Spec coverage:**
- profile resolution + fast knob defaults (setdefault, explicit wins) → Task 1. ✓
- `--fast` flag + `ALBERT_PROFILE` + apply-before-standalone-default ordering + profile banner → Task 2. ✓
- `ALBERT_RESEARCH_WIDTH` knob in phase_0 (default 3, fast 5, breadth unchanged) → Task 3. ✓
- SKILL.md `--fast` docs → Task 4. ✓
- A/B benchmark (≤0.55 ratio, ≥90% quality, honest caveat) → Task 5. ✓
- No graph/schema/contract change → none of the tasks touch them. ✓
- WEBSEARCH_MAX_TURNS=3 set by profile (no code change needed; sdk_client already reads env) → Task 1 FAST_DEFAULTS. ✓

**2. Placeholder scan:** none — code blocks complete. Task 2 Step 2 and Task 3 Step 3 contain explicit "read the current line; if X then …, if Y then …" instructions (the phase_0 wave-1 line / the import presence are the two things the implementer must confirm against the file), with concrete code for each branch — not TODOs.

**3. Type consistency:** `resolve_profile(args_fast, env)`, `apply_profile(profile, env)`, `FAST_DEFAULTS`, `_research_width()`, `_deliberation_banner(run_dir, profile="thorough")` — names/signatures consistent across tasks and tests; the banner default arg preserves the existing one-arg test. ✓
