# Albert Quality Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three quality fixes to Albert: citable `evidence_refs`, verdict-narrative↔veto coherence, and a standalone `ALBERT_MAX_REWORK=1` default.

**Architecture:** A shared `albert/utils.research_refs()` enumerates research as `[Rk] query → snippet`; phase_2 injects it + the prompt cites it + render shows it + phase_3 verifies against the same ids. phase_4 appends a deterministic note to `reproducible_judgment` when the rule-engine vetoes the LLM action. run_albert sets a standalone rework default.

**Tech Stack:** Python 3, pytest. No schema/graph/contract changes.

---

## Reference (current code)

- `albert/utils.py` has `load_prompt(name)`. Add `research_refs` here (shared by phase_2 + phase_3).
- `phase_2_challenge_generation.py:46` builds ctx with `f"Research:\n{_lines([r.get('results') ...], 3)}\n"` — replace that one line. Challenge dicts carry optional `evidence_refs` (list of str) per `schemas._CHALLENGE_ITEM`.
- `phase_3_self_critique_audit.py:86` builds `digest = "\n".join(f"- {r.get('query','')}: {str(r.get('results',''))[:300]}" for r in research[:6])` — replace with the shared helper.
- `albert/deliberation.py render_challenges` builds each challenge card with two lines (`拷問:` / `為何問:`).
- `phase_4_signals_action_gate.py:49-53` sets `recommended_next_action` (via `enforce_action_consistency`) and `reproducible_judgment`. `res.get("proposed_next_action", ...)` is the LLM proposal.
- `run_albert.py`: `ai = build_input(...)` → `ai["mode"]` ("standalone"|"cockpit"); graph built at line ~47, invoked at ~56. `graph._max_rework()` reads `os.environ["ALBERT_MAX_REWORK"]` at invoke-time (default 2).

---

## Task 1: `evidence_refs` end-to-end (citable research)

**Files:**
- Modify: `albert/utils.py`, `albert/phases/phase_2_challenge_generation.py`,
  `albert/prompts/challenge_generation.txt`, `albert/deliberation.py`,
  `albert/phases/phase_3_self_critique_audit.py`
- Test: `tests/test_evidence_refs.py`, plus a render assert in `tests/test_deliberation.py`

- [ ] **Step 1: Write the failing test** `tests/test_evidence_refs.py`:

```python
from albert.utils import research_refs
from albert import deliberation as D


def test_research_refs_enumerates_with_ids():
    research = [{"query": "TC4 roadmap", "results": "AURIX TC4 targets high-end ZCU\nmore text"},
                {"query": "S32G3 successor", "results": "NXP S32G3 ships now"}]
    out = research_refs(research)
    assert "[R1] TC4 roadmap → AURIX TC4 targets high-end ZCU more text" in out
    assert "[R2] S32G3 successor → NXP S32G3 ships now" in out


def test_research_refs_caps_and_truncates():
    research = [{"query": f"q{i}", "results": "x" * 500} for i in range(12)]
    out = research_refs(research, limit=8, snip=180)
    assert "[R8]" in out and "[R9]" not in out          # capped at 8
    assert "x" * 181 not in out                          # snippet truncated


def test_render_challenges_shows_evidence_refs():
    state = {"top_ambiguities": [], "albert_challenges": [
        {"bone": 2, "challenge": "c", "why_albert_would_ask": "w", "severity": "high",
         "current_answer_strength": "weak", "evidence_refs": ["R1", "R3"]}]}
    out = D.render_challenges(state)
    assert "證據:R1, R3" in out


def test_render_challenges_omits_evidence_line_when_empty():
    state = {"top_ambiguities": [], "albert_challenges": [
        {"bone": 2, "challenge": "c", "why_albert_would_ask": "w", "severity": "high",
         "current_answer_strength": "weak", "evidence_refs": []}]}
    out = D.render_challenges(state)
    assert "證據:" not in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_evidence_refs.py -v`
Expected: FAIL (`research_refs` not in utils; render has no 證據 line).

- [ ] **Step 3: Add `research_refs` to `albert/utils.py`** (append):

```python
def research_refs(research, limit: int = 8, snip: int = 180) -> str:
    """Enumerate research findings as stable [Rk] refs the LLM can cite in
    evidence_refs and the self-critique can verify against."""
    lines = []
    for i, r in enumerate((research or [])[:limit], 1):
        q = str(r.get("query", "")).strip()
        res = " ".join(str(r.get("results", "")).split())[:snip]
        lines.append(f"[R{i}] {q} → {res}")
    return "\n".join(lines)
```

- [ ] **Step 4: Use it in `phase_2_challenge_generation.py`** — add the import and replace the `Research:` context line.

Add to imports at top:
```python
from albert.utils import load_prompt, research_refs
```
(Replace the existing `from albert.utils import load_prompt` line.)

Replace the final ctx line:
```python
           f"Research:\n{_lines([r.get('results') for r in state.get('research', [])], 3)}\n")
```
with:
```python
           f"Research (cite these ids in each challenge's evidence_refs):\n"
           f"{research_refs(state.get('research', []))}\n")
```

- [ ] **Step 5: Instruct the prompt** — append to `albert/prompts/challenge_generation.txt` (before the final 繁體中文 line, or after it — order doesn't matter):

```
For each challenge, set evidence_refs to the [Rk] id(s) from the Research section that ground or directly relate to it (at most 2; cite the id only, e.g. "R1"; leave empty if none genuinely apply — do NOT invent a citation).
```

- [ ] **Step 6: Render the refs** in `albert/deliberation.py` `render_challenges` — change the per-challenge card body to include an evidence line when present:

```python
    for i, c in enumerate(chs, 1):
        meta = (f"骨#{c.get('bone', '?')} · 嚴重度:{L.sev_zh(c.get('severity'))}"
                f" · 現答:{L.strength_zh(c.get('current_answer_strength'))}")
        lines = [f"拷問:{c.get('challenge', '')}",
                 f"為何問:{c.get('why_albert_would_ask', '')}"]
        refs = c.get("evidence_refs") or []
        if refs:
            lines.append(f"證據:{', '.join(str(r) for r in refs)}")
        out.append(L.card(i, len(chs), meta, lines))
```

- [ ] **Step 7: Align phase_3 digest** in `phase_3_self_critique_audit.py` — add the import and replace the digest line.

Add import near the other albert imports:
```python
from albert.utils import load_prompt, research_refs
```
(Replace the existing `from albert.utils import load_prompt` line.)

Replace:
```python
    digest = "\n".join(f"- {r.get('query','')}: {str(r.get('results',''))[:300]}" for r in research[:6])
```
with:
```python
    digest = research_refs(research, limit=8, snip=300)
```

- [ ] **Step 8: Run tests**

Run: `py -3 -m pytest tests/test_evidence_refs.py -v`
Expected: PASS (4 passed).

- [ ] **Step 9: Full suite**

Run: `py -3 -m pytest -q`
Expected: PASS, no regressions (was 157).

- [ ] **Step 10: Commit**

```bash
git -c commit.gpgsign=false add albert/utils.py albert/phases/phase_2_challenge_generation.py albert/prompts/challenge_generation.txt albert/deliberation.py albert/phases/phase_3_self_critique_audit.py tests/test_evidence_refs.py
git -c commit.gpgsign=false commit -m "feat(evidence): citable [Rk] research refs — populate+render+verify evidence_refs"
```

---

## Task 2: Verdict narrative ↔ signal-veto coherence

**Files:**
- Modify: `albert/phases/phase_4_signals_action_gate.py`
- Test: `tests/test_veto_note.py`

- [ ] **Step 1: Write the failing test** `tests/test_veto_note.py`:

```python
from albert import deliberation
from albert.phases import phase_4_signals_action_gate as p4


def _run_with(monkeypatch, tmp_path, res):
    deliberation.init(tmp_path)
    monkeypatch.setattr(p4, "call_claude", lambda **k: res)
    state = {"current_answer": "x", "albert_challenges": [], "research_state": {}}
    return p4.phase_4_signals_action_gate(state)


def test_note_appended_when_vetoed(tmp_path, monkeypatch):
    # premature_end high (open high-impact challenge) + proposed synthesize -> veto to continue_research
    res = {"premature_end_atoms": {"open_high_impact_challenges": 3, "new_info_rate": "high"},
           "drift_atoms": {}, "proposed_next_action": "synthesize",
           "reproducible_judgment": "建議 synthesize。",
           "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []}}
    state = _run_with(monkeypatch, tmp_path, res)
    assert state["recommended_next_action"] == "continue_research"
    assert "經訊號否決改為 continue_research" in state["reproducible_judgment"]
    assert "synthesize" in state["reproducible_judgment"]


def test_no_note_when_not_vetoed(tmp_path, monkeypatch):
    res = {"premature_end_atoms": {"open_high_impact_challenges": 0, "new_info_rate": "low",
           "challenge_map_mostly_classified": True, "unresolved_are_human_data_decision_only": True},
           "drift_atoms": {"current_focus_in_original_high_value_set": True, "high_value_branch_ignored": False},
           "proposed_next_action": "synthesize", "reproducible_judgment": "建議 synthesize。",
           "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []}}
    state = _run_with(monkeypatch, tmp_path, res)
    assert state["recommended_next_action"] == "synthesize"
    assert "經訊號否決" not in state["reproducible_judgment"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_veto_note.py -v`
Expected: FAIL (`test_note_appended_when_vetoed` — note not present).

- [ ] **Step 3: Implement** in `phase_4_signals_action_gate.py`. The current lines are:

```python
    state["recommended_next_action"] = enforce_action_consistency(
        res.get("proposed_next_action", "continue_research"), pe_level, dr_level, state["missing_evidence"])
    state["rationale"] = res.get("rationale") or ""
    state["decision_gate"] = res.get("decision_gate") or dict(_STUB["decision_gate"])
    state["reproducible_judgment"] = res.get("reproducible_judgment") or ""
```

Change to (capture the proposed action, then append a note to reproducible_judgment if vetoed):

```python
    _proposed = res.get("proposed_next_action", "continue_research")
    state["recommended_next_action"] = enforce_action_consistency(
        _proposed, pe_level, dr_level, state["missing_evidence"])
    state["rationale"] = res.get("rationale") or ""
    state["decision_gate"] = res.get("decision_gate") or dict(_STUB["decision_gate"])
    _rj = res.get("reproducible_judgment") or ""
    if state["recommended_next_action"] != _proposed:
        _rj = (_rj + f"（註:LLM 原建議 {_proposed},經訊號否決改為 "
                     f"{state['recommended_next_action']}。）")
    state["reproducible_judgment"] = _rj
```

- [ ] **Step 4: Run tests**

Run: `py -3 -m pytest tests/test_veto_note.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Full suite**

Run: `py -3 -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git -c commit.gpgsign=false add albert/phases/phase_4_signals_action_gate.py tests/test_veto_note.py
git -c commit.gpgsign=false commit -m "fix(signals): note signal-veto override in reproducible_judgment (narrative↔action coherence)"
```

---

## Task 3: Standalone default `ALBERT_MAX_REWORK=1`

**Files:**
- Modify: `run_albert.py`
- Test: `tests/test_rework_default.py`

- [ ] **Step 1: Write the failing test** `tests/test_rework_default.py`:

```python
import importlib
run_albert = importlib.import_module("run_albert")


def test_standalone_sets_default_when_unset():
    env = {}
    run_albert._apply_standalone_rework_default("standalone", env)
    assert env["ALBERT_MAX_REWORK"] == "1"


def test_standalone_respects_explicit_env():
    env = {"ALBERT_MAX_REWORK": "3"}
    run_albert._apply_standalone_rework_default("standalone", env)
    assert env["ALBERT_MAX_REWORK"] == "3"


def test_cockpit_unchanged():
    env = {}
    run_albert._apply_standalone_rework_default("cockpit", env)
    assert "ALBERT_MAX_REWORK" not in env
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_rework_default.py -v`
Expected: FAIL (`_apply_standalone_rework_default` not defined).

- [ ] **Step 3: Implement** in `run_albert.py` — add the helper at module level (near the top, after imports):

```python
def _apply_standalone_rework_default(mode, env):
    """Standalone runs are interactive — default to one rework pass unless the
    caller set ALBERT_MAX_REWORK explicitly. Cockpit mode keeps the graph default (2)."""
    if mode == "standalone" and "ALBERT_MAX_REWORK" not in env:
        env["ALBERT_MAX_REWORK"] = "1"
```

Then call it right after `ai = build_input(...)` and before `graph.invoke(...)`. Locate:
```python
            ai = build_input(raw_text=args.proposal, input_json=args.input_json)
```
and add immediately after it:
```python
            _apply_standalone_rework_default(ai["mode"], os.environ)
```
(`os` is already imported in run_albert.py — confirm; if not, add `import os` at top.)

- [ ] **Step 4: Run tests**

Run: `py -3 -m pytest tests/test_rework_default.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Full suite + CLI smoke**

Run: `py -3 -m pytest -q` (expect green) and `py -3 run_albert.py --help` (loads cleanly).

- [ ] **Step 6: Commit**

```bash
git -c commit.gpgsign=false add run_albert.py tests/test_rework_default.py
git -c commit.gpgsign=false commit -m "feat(cli): standalone defaults ALBERT_MAX_REWORK=1 (cockpit/explicit unchanged)"
```

---

## Self-Review

**1. Spec coverage:**
- #1 evidence_refs: research_refs helper + phase_2 ctx + prompt + render + phase_3 digest → Task 1. ✓
- #2 veto coherence: phase_4 note → Task 2. ✓
- #3 standalone rework default → Task 3. ✓

**2. Placeholder scan:** none — all code blocks complete.

**3. Type consistency:** `research_refs(research, limit=8, snip=...)` defined in Task 1 Step 3, used identically in Task 1 Step 4/Step 7. `_apply_standalone_rework_default(mode, env)` defined and called consistently. evidence_refs read as a list of str in render + test. phase_4 `_proposed`/`_rj` locals consistent. ✓
