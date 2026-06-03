# Albert Flash Mode (one Opus call, bypass all flow) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 4th profile `flash` — one Opus call, no research, bypassing phase_0/2/3/4 (graph `START → phase_flash → p5`).

**Architecture:** Extract `phase_quick_combined`'s one-call core into `combined_audit` (shared); `phase_quick_combined` becomes a thin wrapper; new `phase_flash` calls `combined_audit` with no research after copying intake fields from `albert_input`. Graph `START` becomes conditional (flash bypasses p0). Reuses QUICK_COMBINED schema, apply_signals, p5.

**Tech Stack:** Python 3, pytest, LangGraph.

---

## Reference (verified current code)

- `albert/phases/phase_quick_combined.py` (full current body — the source for the extraction):
  imports `sys, VisibilityContractError, call_claude, model_for_role, load_prompt, research_refs,
  schemas, deliberation, delib_layout as L, apply_signals`; module `_STUB`; builds ctx (with a
  Research section), one `call_claude(QUICK_COMBINED, albert_persona+quick_combined)`, sets
  albert_challenges/weak_points/missing_business_context/would_survive_leadership/top_ambiguities
  (pad to 3), `apply_signals`, `verdict="exhausted"`, `phase_2_status`, `phase_4_status/_complete`,
  builds body = `L.header("PHASE Q …") + render_challenges(header=False) + note +
  render_signals(header=False) + render_verdict(header=False)`, `deliberation.block("phase_quick_combined", banner, body)`.
- `albert/profile.py`: `FAST_DEFAULTS`, `QUICK_DEFAULTS`, `_PROFILE_DEFAULTS={"fast":...,"quick":...}`,
  `resolve_profile(args_fast, env)` (lowercases env ALBERT_PROFILE), `apply_profile(profile, env)`
  (table-driven setdefault).
- `albert/graph.py`: `g.add_edge(START, "phase_0_intake_grounding")` then `_route_after_intake`
  conditional after p0; nodes wrapped via `_wrap`; `_route_from_start` does NOT exist yet.
- `run_albert.py`: profile block (lines ~78-86) sets `profile` from `--quick`/`--fast`/env, applies
  it; `initial = {..., "profile": profile}`; `AlbertState` declares `profile`.

---

## Task 1: profile.py — add `flash`

**Files:** Modify `albert/profile.py`; Test `tests/test_profile.py` (append)

- [ ] **Step 1: Append tests:**
```python
def test_resolve_flash():
    from albert.profile import resolve_profile
    assert resolve_profile(False, {"ALBERT_PROFILE": "flash"}) == "flash"


def test_apply_flash_sets_maxrework():
    from albert.profile import apply_profile, FLASH_DEFAULTS
    env = {}
    apply_profile("flash", env)
    assert env["ALBERT_MAX_REWORK"] == "0"
    assert "ALBERT_MAX_REWORK" in FLASH_DEFAULTS
```
- [ ] **Step 2: Run → FAIL** (`FLASH_DEFAULTS` missing).
- [ ] **Step 3:** in `albert/profile.py`, add after `QUICK_DEFAULTS`:
```python
FLASH_DEFAULTS = {"ALBERT_MAX_REWORK": "0"}
```
and update the table:
```python
_PROFILE_DEFAULTS = {"fast": FAST_DEFAULTS, "quick": QUICK_DEFAULTS, "flash": FLASH_DEFAULTS}
```
- [ ] **Step 4: Run → PASS.** `py -3 -m pytest tests/test_profile.py -v`
- [ ] **Step 5: Commit:** `git -c commit.gpgsign=false add albert/profile.py tests/test_profile.py && git -c commit.gpgsign=false commit -m "feat(profile): flash profile (MAX_REWORK=0)"`

---

## Task 2: Extract `combined_audit` + refactor phase_quick_combined

**Files:** Create `albert/phases/_combined.py`; Modify `albert/phases/phase_quick_combined.py`; Test: existing `tests/test_phase_quick_combined.py` (guards the refactor — no new test needed, but it MUST stay green)

- [ ] **Step 1:** Create `albert/phases/_combined.py`:
```python
"""Shared one-call audit core for quick + flash profiles.

ONE call_claude(QUICK_COMBINED) + apply_signals + contract fields + deliberation block.
quick passes research_text (from research_refs); flash passes "" (no research)."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt
from albert import schemas, deliberation
from albert import delib_layout as L
from albert.signals_apply import apply_signals

_STUB = {"albert_challenges": [{"challenge": "(LLM unavailable — re-run Albert)",
         "why_albert_would_ask": "n/a", "status": "blocked", "severity": "high",
         "current_answer_strength": "weak", "generator": "winning", "bone": 2}],
         "weak_points": [], "missing_business_context": [], "would_survive_leadership": False,
         "top_ambiguities": [{"term": "(LLM unavailable)", "why_dangerous": "n/a",
                              "precise_question": "re-run"} for _ in range(3)],
         "premature_end_atoms": {}, "drift_atoms": {}, "proposed_next_action": "continue_research",
         "decision_gate": {"can_decide_now": [], "cannot_decide": ["(LLM unavailable)"], "owners": []},
         "reproducible_judgment": "", "verdict_standalone": "產品定義不完整", "light": "red",
         "readiness_score_delta": -2}


def combined_audit(state: dict, *, prompt: str, node: str, banner: str,
                   research_text: str, note: str) -> dict:
    ctx = (f"Output purpose: {state.get('output_purpose','')}\n\n"
           f"Current answer:\n{state.get('current_answer','')[:6000]}\n")
    if research_text:
        ctx += f"\nResearch (cite [Rk] in evidence_refs):\n{research_text}\n"
    status = "passed"
    try:
        res = call_claude(model=model_for_role("challenge_generation"),
                          system=load_prompt("albert_persona") + "\n\n" + load_prompt(prompt),
                          user=ctx, json_schema=schemas.QUICK_COMBINED, purpose=prompt)
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] {node} failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = dict(_STUB), "failed"
    state["albert_challenges"] = res.get("albert_challenges") or _STUB["albert_challenges"]
    state["weak_points"] = res.get("weak_points") or []
    state["missing_business_context"] = res.get("missing_business_context") or []
    state["would_survive_leadership"] = bool(res.get("would_survive_leadership", False))
    amb = res.get("top_ambiguities") or []
    if not isinstance(amb, list) or len(amb) < 3:
        amb = (amb if isinstance(amb, list) else []) + _STUB["top_ambiguities"]
    state["top_ambiguities"] = amb[:3]
    apply_signals(state, res)
    state["verdict"] = "exhausted"
    state["phase_2_status"] = status
    state["phase_4_status"], state["phase_4_complete"] = status, True
    body = (L.header(banner)
            + "\n" + deliberation.render_challenges(state, header=False)
            + f"\n\n{note}\n\n"
            + deliberation.render_signals({
                "premature_end_risk": state["premature_end_risk"],
                "research_drift_risk": state["research_drift_risk"],
                "proposed_next_action": res.get("proposed_next_action", "?"),
                "recommended_next_action": state["recommended_next_action"]}, header=False)
            + "\n\n" + deliberation.render_verdict({
                "verdict_standalone": state["verdict_standalone"], "light": state["light"],
                "readiness_score_delta": state["readiness_score_delta"],
                "recommended_next_action": state["recommended_next_action"],
                "reproducible_judgment": state["reproducible_judgment"]}, header=False))
    deliberation.block(node, banner, body)
    return state
```

- [ ] **Step 2:** Replace the ENTIRE body of `albert/phases/phase_quick_combined.py` with the thin wrapper:
```python
"""Quick mode: ONE Opus call (challenges + inline self-critique + signals + verdict),
no separate debate/rework round. Thin wrapper over combined_audit (shared with flash)."""
from albert.utils import research_refs
from albert.phases._combined import combined_audit


def phase_quick_combined(state: dict) -> dict:
    return combined_audit(
        state, prompt="quick_combined", node="phase_quick_combined",
        banner="PHASE Q ─ 快速審查(quick)",
        research_text=research_refs(state.get("research", [])),
        note="(quick 模式:單次審查 + inline 自我檢查,無多票辯論)")
```

- [ ] **Step 3: Run** `py -3 -m pytest tests/test_phase_quick_combined.py -v` → both tests still PASS (refactor is behavior-preserving; quick still emits "PHASE Q" banner + populates contract). Full suite `py -3 -m pytest -q` → no regressions (was 205).
- [ ] **Step 4: Commit:** `git -c commit.gpgsign=false add albert/phases/_combined.py albert/phases/phase_quick_combined.py && git -c commit.gpgsign=false commit -m "refactor(quick): extract combined_audit (shared by quick + flash)"`

---

## Task 3: flash prompt + phase_flash

**Files:** Create `albert/prompts/flash_combined.txt`, `albert/phases/phase_flash.py`; Test `tests/test_phase_flash.py`

- [ ] **Step 1: Create `albert/prompts/flash_combined.txt`** (UTF-8):
```
You are Albert in FLASH mode — ONE shot, no external research. Give your best one-shot judgment of the CURRENT ANSWER from the proposal alone. In ONE response:
1. The 3 most dangerous ambiguities (term / why_dangerous / precise_question).
2. Up to 6 high-impact 拷問 (albert_challenges) — challenge, why_albert_would_ask, status, severity, current_answer_strength, generator, bone. evidence_refs MUST be empty (no research was done).
3. weak_points, would_survive_leadership.
4. signals atoms (premature_end_atoms, drift_atoms), recommended_next_probe (what you'd verify), missing_evidence (what's unverified — be honest, you had no research), questions_albert_would_ask, proposed_next_action, rationale, decision_gate, reproducible_judgment.
5. verdict_standalone (可推進/要補證據/方向錯/產品定義不完整), light (green/yellow/red), readiness_score_delta (-2..2).
You had NO web research — surface what you would verify rather than asserting facts. Be decisive and concise. Emit StructuredOutput.
以繁體中文輸出。技術名詞(TC4, ASIL, Ethernet, AUTOSAR, gateway, MCU, zonal, OEM…)保留英文原文,不要硬翻。
```

- [ ] **Step 2: Failing test** `tests/test_phase_flash.py`:
```python
from albert import deliberation
from albert.phases import phase_flash as pf
from albert.phases import _combined


def _stub_res():
    return {"albert_challenges": [{"bone": 2, "challenge": "c", "why_albert_would_ask": "w",
            "severity": "high", "current_answer_strength": "weak", "generator": "winning",
            "status": "needs_bu_judgment"}],
            "weak_points": ["wp"], "would_survive_leadership": False,
            "top_ambiguities": [{"term": "t", "why_dangerous": "d", "precise_question": "q"},
                                {"term": "t2", "why_dangerous": "d", "precise_question": "q"},
                                {"term": "t3", "why_dangerous": "d", "precise_question": "q"}],
            "premature_end_atoms": {"open_high_impact_challenges": 2, "new_info_rate": "high"},
            "drift_atoms": {}, "proposed_next_action": "continue_research",
            "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
            "reproducible_judgment": "j", "verdict_standalone": "要補證據",
            "light": "yellow", "readiness_score_delta": 0}


def test_flash_populates_contract_from_albert_input(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    monkeypatch.setattr(_combined, "call_claude", lambda **k: _stub_res())
    state = {"albert_input": {"current_answer": "MY PROPOSAL TEXT", "mode": "standalone",
                              "output_purpose": "meeting_defense", "proposal": {"title": "P"}}}
    out = pf.phase_flash(state)
    assert out["current_answer"] == "MY PROPOSAL TEXT"   # copied from albert_input (p0 skipped)
    assert out["research"] == []
    assert out["verdict_standalone"] == "要補證據"
    assert out["verdict"] == "exhausted"
    assert out["phase_4_status"] == "passed"
    md = (tmp_path / "deliberation.md").read_text(encoding="utf-8")
    assert "PHASE F ─ 閃電審查" in md
    assert "PHASE 0 ─ 研究" not in md


def test_flash_degraded_on_failure(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    def boom(**k): raise RuntimeError("down")
    monkeypatch.setattr(_combined, "call_claude", boom)
    state = {"albert_input": {"current_answer": "x", "mode": "standalone"}}
    out = pf.phase_flash(state)
    assert out["phase_4_status"] == "failed"
    assert deliberation.emitted("phase_flash")
```
Run → FAIL.

- [ ] **Step 3: Create `albert/phases/phase_flash.py`:**
```python
"""Flash mode: ONE Opus call, NO research, bypasses phase_0/2/3/4. Albert's one-shot judgment."""
from albert.phases._combined import combined_audit


def phase_flash(state: dict) -> dict:
    inp = state.get("albert_input") or {}
    state.setdefault("current_answer", inp.get("current_answer", ""))
    state["output_purpose"] = state.get("output_purpose") or inp.get("output_purpose", "")
    state["original_objective"] = state.get("original_objective") or inp.get("original_objective", "")
    state["meeting_context"] = state.get("meeting_context") or inp.get("meeting_context", "")
    state["proposal"] = state.get("proposal") or inp.get("proposal", {}) or {}
    state["research"] = []
    return combined_audit(
        state, prompt="flash_combined", node="phase_flash",
        banner="PHASE F ─ 閃電審查(flash)", research_text="",
        note="(flash 模式:單次 Opus 判斷,無研究、無辯論)")
```
NOTE: the test monkeypatches `_combined.call_claude` (combined_audit calls `call_claude` imported into `_combined`), so patching there is correct.

- [ ] **Step 4: Run** `py -3 -m pytest tests/test_phase_flash.py -v` → PASS (2). Full suite green.
- [ ] **Step 5: Commit:** `git -c commit.gpgsign=false add albert/prompts/flash_combined.txt albert/phases/phase_flash.py tests/test_phase_flash.py && git -c commit.gpgsign=false commit -m "feat(flash): flash_combined prompt + phase_flash (one call, no research)"`

---

## Task 4: graph conditional START + --flash + precedence

**Files:** Modify `albert/graph.py`, `run_albert.py`; Test `tests/test_flash_route.py`

- [ ] **Step 1: Failing test** `tests/test_flash_route.py`:
```python
from albert.graph import _route_from_start
from albert.state import AlbertState


def test_route_from_start_flash():
    assert _route_from_start({"profile": "flash"}) == "phase_flash"


def test_route_from_start_default():
    assert _route_from_start({"profile": "thorough"}) == "phase_0_intake_grounding"
    assert _route_from_start({}) == "phase_0_intake_grounding"


def test_flash_route_survives_state_filter():
    initial = {"profile": "flash", "mode": "standalone", "_x": 1}
    kept = {k: v for k, v in initial.items() if k in AlbertState.__annotations__}
    assert _route_from_start(kept) == "phase_flash"
```
Run → FAIL.

- [ ] **Step 2: graph.py** — add import `from albert.phases.phase_flash import phase_flash`; add router:
```python
def _route_from_start(state: dict) -> str:
    return "phase_flash" if state.get("profile") == "flash" else "phase_0_intake_grounding"
```
Add `("phase_flash", phase_flash),` to the `_wrap` node list. Replace `g.add_edge(START, "phase_0_intake_grounding")` with:
```python
    g.add_conditional_edges(START, _route_from_start,
        {"phase_flash": "phase_flash",
         "phase_0_intake_grounding": "phase_0_intake_grounding"})
    g.add_edge("phase_flash", "phase_5_assemble_render")
```
Leave the `_route_after_intake` conditional (after p0) and all other edges unchanged.

- [ ] **Step 3: run_albert.py** — add `--flash` flag (after `--quick`): `ap.add_argument("--flash", action="store_true")`. Replace the profile block with precedence flash>quick>fast:
```python
    if args.flash:
        profile = "flash"
    elif args.quick:
        profile = "quick"
    else:
        profile = resolve_profile(args.fast, os.environ)
    _extra = [n for n, on in (("--flash", args.flash), ("--quick", args.quick), ("--fast", args.fast)) if on]
    if len(_extra) > 1:
        sys.stderr.write(f"[profile] multiple given {_extra}; using {profile}\n")
    _applied = apply_profile(profile, os.environ)
    if profile in ("fast", "quick", "flash"):
        sys.stderr.write(f"[profile] {profile} — {', '.join(f'{k}={v}' for k, v in _applied.items()) or '(all pre-set)'}\n")
```
(`profile` is already added to the `initial` state dict and passed to the banner — no change there.)

- [ ] **Step 4: Run** `py -3 -m pytest tests/test_flash_route.py -v` → PASS. Full suite `py -3 -m pytest -q` → green. Verify graph compiles: `py -3 -c "from albert.graph import build_graph; build_graph(); print('ok')"`. Smoke: `py -3 run_albert.py "x" --flash --dry-run --allow-redirect` → `[profile] flash — ALBERT_MAX_REWORK=0` + dry-run line. `py -3 run_albert.py --help` shows `--flash`.
- [ ] **Step 5: Commit:** `git -c commit.gpgsign=false add albert/graph.py run_albert.py tests/test_flash_route.py && git -c commit.gpgsign=false commit -m "feat(flash): conditional START routes flash to phase_flash; --flash flag + precedence"`

---

## Task 5: SKILL.md doc

**Files:** Modify `SKILL.md`

- [ ] **Step 1:** After the "Quick mode(`--quick`)" section add:
```markdown
## Flash mode(`--flash`)

最快:一次 Opus 呼叫、**完全不查研究、跳過所有 phase**(`START → flash → 裁決`):

    py -3 run_albert.py "<你的提案>" --flash

這是 Albert 的「一眼直覺判斷」(~1-2 分鐘):沒有研究佐證、沒有辯論,只憑提案本身。最省時、品質最低,
適合即時 sanity check。prompt 會要 Albert 把「無法佐證的點」列進 missing_evidence,所以缺口看得到。
正式決策請用 thorough / `--fast`。多個 flag 同時給時優先序:flash > quick > fast。
```
- [ ] **Step 2: Commit:** `git -c commit.gpgsign=false add SKILL.md && git -c commit.gpgsign=false commit -m "docs: document --flash (one-call, no-research) mode"`

---

## Task 6: Flash benchmark

**Files:** Modify `docs/speedup-results.md`

- [ ] **Step 1:** Run flash on the same bench proposal: `py -3 run_albert.py "<bench proposal>" --flash --allow-redirect` (set `PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONDONTWRITEBYTECODE=1`). Confirm graph nodes executed = `phase_flash`, `phase_5_assemble_render` only (read `runs/<id>/progress.jsonl` phase_start events — NO phase_0/2/3/4). Capture wall-clock + verdict fields.
- [ ] **Step 2:** Append a "## Flash mode (2026-06-03)" section to `docs/speedup-results.md`: wall-clock + ratio vs thorough(1082s)/fast(835s)/quick(359s); confirm nodes=[phase_flash, p5]; quality note (one-shot, no research, evidence_refs empty by design). Target: ~1-2 min.
- [ ] **Step 3: Commit:** `git -c commit.gpgsign=false add docs/speedup-results.md && git -c commit.gpgsign=false commit -m "docs(bench): flash mode wall-clock + one-shot quality note"`

---

## Self-Review

**1. Spec coverage:** flash profile (T1); combined_audit extraction + quick wrapper (T2); flash prompt + phase_flash with intake-copy + no research (T3); conditional START + flash node + --flash + precedence + state-filter regression test (T4); SKILL.md (T5); benchmark (T6). Reuses QUICK_COMBINED/apply_signals/p5; profile already in AlbertState + initial state. ✓

**2. Placeholder scan:** none — full code in every step.

**3. Type consistency:** `combined_audit(state, *, prompt, node, banner, research_text, note)` defined T2, called identically by quick wrapper (T2) and phase_flash (T3). `_route_from_start` defined T4 graph + tested T4. `FLASH_DEFAULTS` T1. The flash test monkeypatches `_combined.call_claude` (where combined_audit looks it up) — correct. flash sets phase_2_status+phase_4_status (via combined_audit) so phase_5 degraded detection + render work. ✓
