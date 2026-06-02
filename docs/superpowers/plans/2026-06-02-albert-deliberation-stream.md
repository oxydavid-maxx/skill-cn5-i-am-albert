# Albert Deliberation Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream Albert's full reasoning chain (research → challenges → self-critique debate → rework → verdict) live to the terminal as a human-readable transcript, hard-required so a silent soul phase fails the run.

**Architecture:** A new `albert/deliberation.py` fail-closed emitter mirrors `albert/progress.py` (markdown file + flushed stderr, `VisibilityContractError` on sink failure, emitted-phase tracking). Each soul phase renders a narrative block from its EXISTING structured output (no new LLM calls). `graph.py._wrap` calls `deliberation.assert_emitted(name)` after each soul phase so silence fails closed. `run_albert.py` calls `deliberation.init(run_dir)` and forces unbuffered output.

**Tech Stack:** Python 3, pytest, LangGraph (existing), the existing `albert.errors.VisibilityContractError` contract.

---

## Reference: existing patterns to mirror

- `albert/progress.py` — module-level singleton with `init(run_dir)`, `emit(...)`, a `_progress_path` global, append-to-file + `sys.stderr.write(...)` + `flush()`, raising `VisibilityContractError(message, phase=, sink=)` on any sink failure. **Mirror this structure exactly.**
- `albert/errors.py` — `VisibilityContractError(message, *, phase="", sink="")`. Reuse as-is.
- `albert/graph.py._wrap` (lines 31-51) — wraps each node: `emit_phase_start_summary`; `_p.phase_start`; `result = fn(state)`; `emit_stage_summary`; `_p.phase_end`. The `assert_emitted` call goes between `result = fn(state)` (validated dict) and `_p.phase_end`.
- Soul phases set their structured output into `state` keys: phase_0 → `state["research"]` (list of `{query, results}`); phase_2 → `state["albert_challenges"]` (list of challenge dicts), `state["top_ambiguities"]`, and may set a rework attempt count; phase_3 → `state["phase_3_rounds"][-1]["votes"]` + `state["phase_3_verdict"]` + `assessment`; phase_4 → signals/verdict merged dict in state; phase_5 → final verdict fields.

---

## Task 1: `deliberation.py` core emitter (file + stderr, fail-closed)

**Files:**
- Create: `albert/deliberation.py`
- Test: `tests/test_deliberation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deliberation.py
import pytest
from pathlib import Path
from albert import deliberation
from albert.errors import VisibilityContractError


def test_block_writes_file_and_stderr(tmp_path, capsys):
    deliberation.init(tmp_path)
    deliberation.block("phase_2_challenge_generation", "Challenges", "bone #1 · why · what")
    md = (tmp_path / "deliberation.md").read_text(encoding="utf-8")
    assert "Challenges" in md
    assert "bone #1" in md
    err = capsys.readouterr().err
    assert "DELIBERATION" in err
    assert "bone #1" in err


def test_emitted_tracks_phases(tmp_path):
    deliberation.init(tmp_path)
    assert deliberation.emitted("phase_3_self_critique_audit") is False
    deliberation.block("phase_3_self_critique_audit", "Self-critique", "vote 1 ...")
    assert deliberation.emitted("phase_3_self_critique_audit") is True


def test_assert_emitted_raises_when_silent(tmp_path):
    deliberation.init(tmp_path)
    with pytest.raises(VisibilityContractError):
        deliberation.assert_emitted("phase_4_signals_action_gate")


def test_assert_emitted_passes_after_block(tmp_path):
    deliberation.init(tmp_path)
    deliberation.block("phase_4_signals_action_gate", "Signals", "premature-end: low")
    deliberation.assert_emitted("phase_4_signals_action_gate")  # no raise


def test_init_resets_emitted_set(tmp_path):
    deliberation.init(tmp_path)
    deliberation.block("phase_2_challenge_generation", "C", "x")
    deliberation.init(tmp_path)  # new run
    assert deliberation.emitted("phase_2_challenge_generation") is False


def test_block_raises_when_dir_unwritable(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    # Point the path at a location that will fail to open for append.
    monkeypatch.setattr(deliberation, "_path", tmp_path / "nonexistent-subdir" / "deliberation.md")
    with pytest.raises(VisibilityContractError):
        deliberation.block("phase_2_challenge_generation", "C", "x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_deliberation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'albert.deliberation'` (or AttributeError).

- [ ] **Step 3: Write minimal implementation**

```python
# albert/deliberation.py
"""Live, hard-required deliberation transcript for Albert runs.

Albert's reasoning chain (research -> challenges -> self-critique debate -> rework
-> verdict) is rendered from each phase's EXISTING structured output and emitted
both to runs/<run_id>/deliberation.md and to flushed stderr, so the user watches
the war-room reasoning live. Emission is fail-closed: a sink failure raises
VisibilityContractError, and a soul phase that produces output without emitting a
block fails the run via assert_emitted() (called by graph._wrap).

Mirrors albert/progress.py. No new LLM calls — phases render what they already have.
"""
import sys
from pathlib import Path
from typing import Optional

from albert.errors import VisibilityContractError

_path: Optional[Path] = None
_emitted: set = set()


def init(run_dir) -> None:
    global _path, _emitted
    _path = Path(run_dir) / "deliberation.md"
    _emitted = set()
    try:
        _path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VisibilityContractError(
            f"Failed to create deliberation directory {_path.parent}: {exc}",
            sink=str(_path.parent),
        ) from exc


def block(phase: str, title: str, body: str) -> None:
    """Append a markdown section to deliberation.md AND stream it to stderr live."""
    md = f"\n## {title}\n\n{body}\n"
    if _path is not None:
        try:
            with open(_path, "a", encoding="utf-8") as f:
                f.write(md)
        except OSError as exc:
            raise VisibilityContractError(
                f"Failed to append deliberation block {_path}: {exc}",
                phase=phase, sink=str(_path),
            ) from exc
    try:
        sys.stderr.write(f"\n━━━ DELIBERATION — {title} ━━━\n{body}\n")
        sys.stderr.flush()
    except Exception as exc:
        raise VisibilityContractError(
            f"Failed to write deliberation block to screen: {exc}",
            phase=phase, sink="screen",
        ) from exc
    _emitted.add(phase)


def emitted(phase: str) -> bool:
    return phase in _emitted


def assert_emitted(phase: str) -> None:
    if phase not in _emitted:
        raise VisibilityContractError(
            f"Soul phase {phase} produced output but emitted no deliberation block "
            f"(deliberation is hard-required)",
            phase=phase, sink="deliberation",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_deliberation.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add albert/deliberation.py tests/test_deliberation.py
git -c commit.gpgsign=false commit -m "feat(deliberation): fail-closed live transcript emitter"
```

---

## Task 2: Render helpers (pure, testable narrative builders)

Pure functions that turn each phase's structured output into a narrative string. Keeping them pure means the per-phase wiring (Task 3) is a one-line `deliberation.block(name, title, render_x(state))` and the rendering is unit-tested without running phases.

**Files:**
- Modify: `albert/deliberation.py`
- Test: `tests/test_deliberation.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_deliberation.py
from albert import deliberation as D


def test_render_research():
    state = {"research": [{"query": "TC4 gateway socket size", "results": "AURIX TC4 targets high-end ZCU ..."}]}
    out = D.render_research(state)
    assert "TC4 gateway socket size" in out
    assert "AURIX TC4" in out


def test_render_challenges():
    state = {"top_ambiguities": [{"term": "mid-tier", "why_dangerous": "undefined", "precise_question": "which OEM?"}],
             "albert_challenges": [{"bone": 3, "challenge": "Who is the customer?",
                                    "why_albert_would_ask": "no named socket", "severity": "high",
                                    "current_answer_strength": "weak"}]}
    out = D.render_challenges(state)
    assert "mid-tier" in out
    assert "bone #3" in out
    assert "Who is the customer?" in out
    assert "high" in out


def test_render_self_critique_debate():
    votes = [
        {"weaknesses": [{"classification": "addressable", "issue": "no volume", "suggested_sharpening": "name SOP"}], "verdict": "rework"},
        {"weaknesses": [{"classification": "residual", "issue": "macro risk"}], "verdict": "exhausted"},
        {"weaknesses": [{"classification": "addressable", "issue": "no volume", "suggested_sharpening": "name SOP"}], "verdict": "rework"},
    ]
    assessment = {"addressable_votes": 2, "degraded": False, "merged": []}
    out = D.render_self_critique(votes, assessment, "REWORK")
    assert "Vote 1" in out and "Vote 2" in out and "Vote 3" in out
    assert "no volume" in out
    assert "2" in out  # the addressable vote count
    assert "REWORK" in out


def test_render_self_critique_degraded():
    votes = [{"weaknesses": [], "verdict": "exhausted", "_fallback": True}]
    assessment = {"addressable_votes": 0, "degraded": True, "merged": []}
    out = D.render_self_critique(votes, assessment, "EXHAUSTED")
    assert "degraded" in out.lower()


def test_render_rework():
    merged = [{"issue": "no volume", "suggested_sharpening": "name the SOP window"}]
    out = D.render_rework(2, merged)
    assert "Round 2" in out
    assert "name the SOP window" in out


def test_render_signals():
    merged = {"premature_end_risk": {"level": "low", "why": "all high-impact open"},
              "research_drift_risk": {"level": "medium", "why": "off original set"},
              "proposed_next_action": "continue_research", "recommended_next_action": "continue_research"}
    out = D.render_signals(merged)
    assert "premature" in out.lower()
    assert "low" in out
    assert "continue_research" in out


def test_render_verdict():
    final = {"verdict_standalone": "要補證據", "light": "yellow",
             "readiness_score_delta": -1, "recommended_next_action": "continue_research",
             "reproducible_judgment": "weak on named socket"}
    out = D.render_verdict(final)
    assert "yellow" in out
    assert "-1" in out
    assert "weak on named socket" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_deliberation.py -k render -v`
Expected: FAIL with `AttributeError: module 'albert.deliberation' has no attribute 'render_research'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to albert/deliberation.py

def render_research(state: dict) -> str:
    research = state.get("research") or []
    if not research:
        return "_(no research recorded)_"
    lines = ["Albert 先問自己:要 audit 這個 thesis,我得先查什麼。Queries fired + findings:"]
    for r in research[:8]:
        q = str(r.get("query", "")).strip()
        res = str(r.get("results", "")).strip().replace("\n", " ")
        lines.append(f"- **{q}** → {res[:200]}")
    return "\n".join(lines)


def render_challenges(state: dict, round_label: str = "") -> str:
    lines = []
    if round_label:
        lines.append(f"_{round_label}_")
    ambs = state.get("top_ambiguities") or []
    if ambs:
        lines.append("**3 個最危險的模糊詞 (先釘死定義):**")
        for a in ambs:
            lines.append(f"- `{a.get('term','')}` — {a.get('why_dangerous','')} → {a.get('precise_question','')}")
    chs = state.get("albert_challenges") or []
    lines.append(f"\n**Albert 生成的拷問 ({len(chs)}):**")
    for c in chs:
        lines.append(
            f"- **bone #{c.get('bone','?')}** · {c.get('challenge','')}\n"
            f"  - 為什麼 Albert 會問: {c.get('why_albert_would_ask','')}\n"
            f"  - severity={c.get('severity','?')} · current-answer={c.get('current_answer_strength','?')}"
        )
    return "\n".join(lines)


def _render_one_vote(i: int, vote: dict) -> str:
    if vote.get("_fallback"):
        return f"- **Vote {i}**: (failed / fell back — no judgment)"
    ws = vote.get("weaknesses") or []
    if not ws:
        return f"- **Vote {i}** (verdict={vote.get('verdict','?')}): no weaknesses flagged"
    parts = [f"- **Vote {i}** (verdict={vote.get('verdict','?')}):"]
    for w in ws:
        cls = w.get("classification", "?")
        issue = w.get("issue", "")
        sharp = w.get("suggested_sharpening", "")
        line = f"    - [{cls}] {issue}"
        if sharp:
            line += f" — 磨利: {sharp}"
        parts.append(line)
    return "\n".join(parts)


def render_self_critique(votes: list, assessment: dict, verdict: str) -> str:
    lines = ["三個獨立 skeptic 對同一組拷問各自攻防 (≥2 同意才算 addressable):"]
    for i, v in enumerate(votes, 1):
        lines.append(_render_one_vote(i, v))
    if assessment.get("degraded"):
        lines.append("\n**裁決: degraded — 所有 vote 都失敗,不驅動 rework。**")
    else:
        k = assessment.get("addressable_votes", 0)
        lines.append(f"\n**裁決: addressable_votes = {k} of {len(votes)} → {verdict}**")
    return "\n".join(lines)


def render_rework(round_n: int, merged: list) -> str:
    lines = [f"**Round {round_n} (rework)** — 這些 sharpenings 還沒被吃掉,所以再繞一圈重生拷問:"]
    for w in (merged or []):
        lines.append(f"- {w.get('issue','')}" + (f" → {w.get('suggested_sharpening','')}" if w.get('suggested_sharpening') else ""))
    if not merged:
        lines.append("- (no merged sharpenings recorded)")
    return "\n".join(lines)


def render_signals(merged: dict) -> str:
    pe = merged.get("premature_end_risk") or {}
    dr = merged.get("research_drift_risk") or {}
    lines = [
        f"- **premature-end risk**: {pe.get('level','?')} — {pe.get('why','')}",
        f"- **research-drift risk**: {dr.get('level','?')} — {dr.get('why','')}",
        f"- proposed action: {merged.get('proposed_next_action','?')}"
        f" → final (after signal veto): {merged.get('recommended_next_action', merged.get('proposed_next_action','?'))}",
    ]
    return "\n".join(lines)


def render_verdict(final: dict) -> str:
    light = final.get("light", "?")
    emoji = {"green": "\U0001F7E2", "yellow": "\U0001F7E1", "red": "\U0001F534"}.get(light, "")
    lines = [
        f"- verdict: {final.get('verdict_standalone','?')} {emoji} ({light})",
        f"- readiness delta: {final.get('readiness_score_delta','?')}",
        f"- recommended next action: {final.get('recommended_next_action','?')}",
        f"- one-line judgment: {final.get('reproducible_judgment','')}",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_deliberation.py -v`
Expected: PASS (all render + core tests).

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add albert/deliberation.py tests/test_deliberation.py
git -c commit.gpgsign=false commit -m "feat(deliberation): pure render helpers for each soul phase"
```

---

## Task 3: Wire each soul phase to emit its block

Add a `deliberation.block(...)` call at the end of each soul phase, rendering from the
phase's own structured output. No new LLM calls.

**Files:**
- Modify: `albert/phases/phase_0_intake_grounding.py`
- Modify: `albert/phases/phase_2_challenge_generation.py`
- Modify: `albert/phases/phase_3_self_critique_audit.py`
- Modify: `albert/phases/phase_4_signals_action_gate.py`
- Modify: `albert/phases/phase_5_assemble_render.py`
- Test: `tests/test_deliberation_phases.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deliberation_phases.py
from pathlib import Path
from albert import deliberation


def test_phase_2_emits_block(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    from albert.phases import phase_2_challenge_generation as p2
    # Stub the LLM call so the phase runs offline and just populates state.
    monkeypatch.setattr(p2, "call_claude", lambda **k: {
        "albert_challenges": [{"bone": 1, "challenge": "c", "why_albert_would_ask": "w",
                               "severity": "high", "current_answer_strength": "weak",
                               "generator": "winning", "status": "needs_bu_judgment"}],
        "weak_points": ["wp"], "would_survive_leadership": False,
        "top_ambiguities": [{"term": "t", "why_dangerous": "d", "precise_question": "q"}]})
    state = {"current_answer": "x", "albert_input": {"current_answer": "x", "mode": "standalone"}}
    p2.phase_2_challenge_generation(state)
    assert deliberation.emitted("phase_2_challenge_generation")
    assert "bone #1" in (tmp_path / "deliberation.md").read_text(encoding="utf-8")


def test_phase_3_emits_debate(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    from albert.phases import phase_3_self_critique_audit as p3
    monkeypatch.setattr(p3, "_one_vote", lambda v, payload, digest: {
        "weaknesses": [{"classification": "addressable", "issue": "no volume", "suggested_sharpening": "name SOP"}],
        "verdict": "rework"})
    state = {"albert_challenges": [{"challenge": "c"}], "research": []}
    p3.phase_3_self_critique_audit(state)
    assert deliberation.emitted("phase_3_self_critique_audit")
    md = (tmp_path / "deliberation.md").read_text(encoding="utf-8")
    assert "Vote 1" in md and "no volume" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_deliberation_phases.py -v`
Expected: FAIL (`assert deliberation.emitted(...)` is False — phases don't emit yet).

- [ ] **Step 3: Implement — phase_0** (add at the very end, before `return state`)

In `albert/phases/phase_0_intake_grounding.py`, add import near the top:
```python
from albert import deliberation
```
Immediately before the final `return state`:
```python
    deliberation.block("phase_0_intake_grounding", "Phase 0 — Research grounding",
                       deliberation.render_research(state))
    return state
```

- [ ] **Step 4: Implement — phase_2**

In `albert/phases/phase_2_challenge_generation.py`, add `from albert import deliberation` near the top. Determine a rework label from the attempt count if present, then emit before `return state`:
```python
    _round = state.get("phase_3_attempt_count", 0)
    _label = f"Round {_round + 1} (rework)" if _round else ""
    deliberation.block("phase_2_challenge_generation", "Phase 2 — Challenge generation",
                       deliberation.render_challenges(state, _label))
    return state
```

- [ ] **Step 5: Implement — phase_3** (emit the debate AND, when REWORK, the rework block)

In `albert/phases/phase_3_self_critique_audit.py`, add `from albert import deliberation`. After `verdict = _converged(assessment)` and the state writes, before `state["phase_3_complete"] = True`:
```python
    deliberation.block("phase_3_self_critique_audit", "Phase 3 — Self-critique debate",
                       deliberation.render_self_critique(votes, assessment, verdict))
    if verdict == "REWORK":
        deliberation.block("phase_3_self_critique_audit", "Rework decision",
                           deliberation.render_rework(state["phase_3_attempt_count"], assessment["merged"]))
```
(The second `block` call reuses the same phase key, so `assert_emitted` is still satisfied; it adds a second visible section.)

- [ ] **Step 6: Implement — phase_4**

In `albert/phases/phase_4_signals_action_gate.py`, add `from albert import deliberation`. Identify the merged signals/verdict dict the phase writes to state (e.g. the result dict it returns / stores). Before `return state` (or before returning the patch), build a dict with the risk fields and emit:
```python
    deliberation.block("phase_4_signals_action_gate", "Phase 4 — Signals & action gate",
                       deliberation.render_signals({
                           "premature_end_risk": state.get("premature_end_risk", {}),
                           "research_drift_risk": state.get("research_drift_risk", {}),
                           "proposed_next_action": state.get("proposed_next_action",
                                                             state.get("recommended_next_action", "?")),
                           "recommended_next_action": state.get("recommended_next_action", "?"),
                       }))
    return state
```
NOTE for implementer: read phase_4 first and map these to the ACTUAL state keys it sets (the spec says it computes risk levels via `signals.py` and emits `verdict_standalone`/`light`/`readiness_score_delta`). Use the real key names; the render helper only needs `level`/`why` inside each risk dict and the two action fields.

- [ ] **Step 7: Implement — phase_5**

In `albert/phases/phase_5_assemble_render.py`, add `from albert import deliberation`. After the final verdict fields are assembled (the dict written to `albert_challenge.json`), before `return state`:
```python
    deliberation.block("phase_5_assemble_render", "Phase 5 — Verdict",
                       deliberation.render_verdict({
                           "verdict_standalone": final.get("verdict_standalone", "?"),
                           "light": final.get("light", "?"),
                           "readiness_score_delta": final.get("readiness_score_delta", "?"),
                           "recommended_next_action": final.get("recommended_next_action", "?"),
                           "reproducible_judgment": final.get("reproducible_judgment", ""),
                       }))
    return state
```
NOTE for implementer: `final` is whatever local dict phase_5 builds for the JSON; map field names to the real ones. If phase_5 reads from `state` rather than a local, read those keys instead.

- [ ] **Step 8: Run tests to verify they pass**

Run: `py -3 -m pytest tests/test_deliberation_phases.py -v`
Expected: PASS (2 passed).

- [ ] **Step 9: Commit**

```bash
git -c commit.gpgsign=false add albert/phases/ tests/test_deliberation_phases.py
git -c commit.gpgsign=false commit -m "feat(deliberation): each soul phase renders+emits its block"
```

---

## Task 4: Hard requirement in graph + init wiring + unbuffered run

**Files:**
- Modify: `albert/graph.py:31-51` (the `_wrap` function)
- Modify: `run_albert.py` (call `deliberation.init`, force unbuffered)
- Test: `tests/test_deliberation_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deliberation_graph.py
import pytest
from albert import deliberation
from albert.graph import _wrap
from albert.errors import VisibilityContractError


def test_wrap_fails_closed_when_phase_silent(tmp_path):
    deliberation.init(tmp_path)

    def silent_phase(state):
        return {"ok": True}  # returns a dict but emits no deliberation block

    wrapped = _wrap("phase_2_challenge_generation", silent_phase)
    with pytest.raises(VisibilityContractError):
        wrapped({"run_dir": str(tmp_path)})


def test_wrap_passes_when_phase_emits(tmp_path):
    deliberation.init(tmp_path)

    def good_phase(state):
        deliberation.block("phase_2_challenge_generation", "C", "x")
        return {"ok": True}

    wrapped = _wrap("phase_2_challenge_generation", good_phase)
    result = wrapped({"run_dir": str(tmp_path)})
    assert result["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_deliberation_graph.py -v`
Expected: FAIL — `test_wrap_fails_closed_when_phase_silent` does NOT raise (no assert_emitted yet).

- [ ] **Step 3: Implement — assert_emitted in `_wrap`**

In `albert/graph.py._wrap`, the soul phases that must deliberate are the five graph nodes. Add the import and the assertion. Change the body of `w(state)` from:
```python
        from albert import progress as _p
        from albert.stage_summary import emit_phase_error, emit_phase_start_summary, emit_stage_summary
        emit_phase_start_summary(name, state)
        _p.phase_start(name, {"state_keys": list(state.keys())[:20]})
        try:
            result = fn(state)
            if not isinstance(result, dict):
                raise TypeError(f"{name} must return dict, got {type(result).__name__}")
            merged = dict(state); merged.update(result)
            result.update(emit_stage_summary(name, merged))
            _p.phase_end(name, {"ok": True})
            return result
```
to:
```python
        from albert import progress as _p
        from albert import deliberation as _d
        from albert.stage_summary import emit_phase_error, emit_phase_start_summary, emit_stage_summary
        emit_phase_start_summary(name, state)
        _p.phase_start(name, {"state_keys": list(state.keys())[:20]})
        try:
            result = fn(state)
            if not isinstance(result, dict):
                raise TypeError(f"{name} must return dict, got {type(result).__name__}")
            _d.assert_emitted(name)  # hard requirement: silent deliberation fails the run
            merged = dict(state); merged.update(result)
            result.update(emit_stage_summary(name, merged))
            _p.phase_end(name, {"ok": True})
            return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_deliberation_graph.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Wire `deliberation.init` + unbuffered output in run_albert.py**

In `run_albert.py`, find where `progress.init(run_dir)` is called and add `deliberation.init(run_dir)` right after it (import `from albert import deliberation` at the top). Near the very top of `main()` (or at import time), force unbuffered streams so the live stream is not buffered:
```python
import os
os.environ.setdefault("PYTHONUNBUFFERED", "1")
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
```
NOTE for implementer: read `run_albert.py` to place these correctly — `deliberation.init` MUST run after the run_dir exists and before `graph.invoke`. If `progress.init` is inside a helper, co-locate `deliberation.init` there.

- [ ] **Step 6: Run the full test suite**

Run: `py -3 -m pytest -q`
Expected: PASS — all prior tests (128) plus the new deliberation tests, no regressions.

- [ ] **Step 7: Commit**

```bash
git -c commit.gpgsign=false add albert/graph.py run_albert.py tests/test_deliberation_graph.py
git -c commit.gpgsign=false commit -m "feat(deliberation): hard-require emission in graph + init + unbuffered run"
```

---

## Task 5: Document the always-on deliberation stream in SKILL.md

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Add a section** after the "Output & contract" section:

```markdown
## Deliberation stream (always on)

Every run streams Albert's full reasoning chain live to the terminal and to
`runs/<run_id>/deliberation.md`: the research grounding, the generated challenges +
3 dangerous ambiguities, the **3-vote self-critique debate** with the ≥2-of-3
convergence ruling, any rework rounds, the signals/risk reasoning, and the final
verdict. Emission is **hard-required** — a soul phase that produces output without
emitting its deliberation block fails the run (`VisibilityContractError`).

Run **foreground, no `tee`, no redirect** so the transcript streams as it is produced:

    py -3 D:/D-claude/skill-cn5-i-am-albert/run_albert.py "<proposal>"
```

- [ ] **Step 2: Commit**

```bash
git -c commit.gpgsign=false add SKILL.md
git -c commit.gpgsign=false commit -m "docs(deliberation): document always-on live deliberation stream"
```

---

## Self-Review

**1. Spec coverage:**
- "DeliberationLog (init/block/assert_emitted/emitted), fail-closed" → Task 1. ✓
- "each soul phase renders narrative from existing structured output" → Task 2 (pure renderers) + Task 3 (wiring). ✓
- "hard requirement via assert_emitted in graph._wrap" → Task 4. ✓
- "deliberation.init in run_albert + unbuffered/live" → Task 4 Step 5. ✓
- "degraded phase still emits (no silent)" → Task 2 `render_self_critique` degraded branch + test `test_render_self_critique_degraded`. ✓
- "rework round visible" → Task 2 `render_rework` + Task 3 Step 5. ✓
- "document in SKILL.md + foreground convention" → Task 5. ✓
- "tests: emitter unit, per-phase emits, graph fails-closed" → Tasks 1, 3, 4. ✓

**2. Placeholder scan:** No TBD/TODO. Two implementer NOTES (phase_4/phase_5 field mapping, run_albert placement) are explicit "read the file and map to real keys" instructions, not placeholders — the render contracts (what keys the helper needs) are fully specified; only the source key names must be confirmed against the actual phase code.

**3. Type consistency:** `block(phase, title, body)`, `emitted(phase)`, `assert_emitted(phase)`, `render_research(state)`, `render_challenges(state, round_label="")`, `render_self_critique(votes, assessment, verdict)`, `render_rework(round_n, merged)`, `render_signals(merged)`, `render_verdict(final)` — names used identically across Tasks 1-3. Module global is `_path` (used in Task 1 impl and the unwritable-dir test). ✓
