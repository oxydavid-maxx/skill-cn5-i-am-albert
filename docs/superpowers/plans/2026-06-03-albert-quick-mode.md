# Albert Quick Mode (~5 min, ~80%) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 3rd profile `quick` (~5 min, ~80%) that collapses analysis into one Opus call — skipping the separate 3-vote debate and signals rounds — alongside unchanged thorough/fast.

**Architecture:** `profile.py` gains `quick` + QUICK_DEFAULTS. Deterministic signals tail is extracted to `signals_apply.apply_signals` (reused by phase_4 and the new combined phase). A new `phase_quick_combined` makes ONE LLM call (merged challenge+signals+verdict schema) then applies signals deterministically. The graph routes `p0 → quick → p5` when `state["profile"]=="quick"`. phase_0 gains a query cap.

**Tech Stack:** Python 3, pytest, LangGraph.

---

## Reference (verified current code)

- `albert/profile.py`: `FAST_DEFAULTS`, `resolve_profile(args_fast, env)`, `apply_profile(profile, env)`.
- `albert/graph.py`: `START → p0 → p2 → p3 →(cond rework)→ p4 → p5 → END`; nodes wrapped via `_wrap`; `build_graph(checkpointer)`.
- `albert/phases/phase_4_signals_action_gate.py`: after its `call_claude`, the deterministic tail uses `premature_end_level, drift_level, build_risk, premature_end_why, drift_why, rank_next_probe, enforce_action_consistency` from `albert.signals`, with `rs = state.get("research_state") or {}` and a `_STUB` dict. It sets: premature_end_risk, research_drift_risk, recommended_next_probe, missing_evidence, questions_albert_would_ask, recommended_next_action (+veto note), rationale, decision_gate, reproducible_judgment, verdict_standalone, light, readiness_score_delta. It also sets `state["phase_4_status"], state["phase_4_complete"]` and emits a deliberation block.
- `albert/render.py build_challenge(state)` reads: verdict, current_answer, would_survive_leadership, top_ambiguities, albert_challenges, weak_points, missing_business_context, missing_evidence, questions_albert_would_ask, premature_end_risk, research_drift_risk, recommended_next_probe, recommended_next_action, rationale, decision_gate, readiness_score_delta, reproducible_judgment, degraded, run_status, verdict_standalone, light.
- `albert/phases/phase_5_assemble_render.py`: degraded = `any(state.get(k)=="failed" for k in _STATUS_KEYS)`; reads verdict_standalone/light/delta; writes json/report; emits verdict deliberation. (So quick must set a status key in `_STATUS_KEYS` — set `phase_2_status` AND `phase_4_status` = "passed"/"failed".)
- `albert/schemas.py`: `CHALLENGE_GENERATION` (albert_challenges/weak_points/missing_business_context/would_survive_leadership/top_ambiguities) and `SIGNALS_VERDICT_MERGED` (signals atoms + proposed_next_action + decision_gate + reproducible_judgment + verdict_standalone/light/readiness_score_delta) both exist.
- `albert/deliberation.py`: `render_challenges(state, round_label="")`, `render_signals(merged)`, `render_verdict(final)`, `block(phase, title, body)`, `assert_emitted`.
- `albert/phases/phase_0_intake_grounding.py`: default path `queries = (plan.get("queries") or [])[:8]` then `parallel_map(websearch, queries, max_workers=_research_width())`.

---

## Task 1: profile.py — add `quick` + QUICK_DEFAULTS

**Files:** Modify `albert/profile.py`; Test `tests/test_profile.py` (append)

- [ ] **Step 1: Append failing tests** to `tests/test_profile.py`:

```python
from albert.profile import QUICK_DEFAULTS


def test_resolve_quick():
    from albert.profile import resolve_profile
    assert resolve_profile(False, {"ALBERT_PROFILE": "quick"}) == "quick"


def test_apply_quick_sets_defaults():
    from albert.profile import apply_profile
    env = {}
    apply_profile("quick", env)
    assert env["ALBERT_MAX_REWORK"] == "0"
    assert env["ALBERT_WEBSEARCH_MAX_TURNS"] == "3"
    assert env["ALBERT_RESEARCH_WIDTH"] == "3"
    assert env["ALBERT_RESEARCH_MAX_QUERIES"] == "3"


def test_apply_quick_respects_explicit():
    from albert.profile import apply_profile
    env = {"ALBERT_RESEARCH_MAX_QUERIES": "8"}
    apply_profile("quick", env)
    assert env["ALBERT_RESEARCH_MAX_QUERIES"] == "8"
```

- [ ] **Step 2: Run → FAIL** (`QUICK_DEFAULTS` missing): `py -3 -m pytest tests/test_profile.py -k quick -v`

- [ ] **Step 3: Implement** in `albert/profile.py` — add `QUICK_DEFAULTS` after `FAST_DEFAULTS`, and generalize `apply_profile` to handle both:

```python
QUICK_DEFAULTS = {
    "ALBERT_MAX_REWORK": "0",
    "ALBERT_WEBSEARCH_MAX_TURNS": "3",
    "ALBERT_RESEARCH_WIDTH": "3",
    "ALBERT_RESEARCH_MAX_QUERIES": "3",
}

_PROFILE_DEFAULTS = {"fast": FAST_DEFAULTS, "quick": QUICK_DEFAULTS}
```

Replace the body of `apply_profile` with:

```python
def apply_profile(profile: str, env) -> dict:
    """Set a profile's knob DEFAULTS into env (setdefault). Explicit env wins.
    thorough/unknown = no-op. Returns the dict actually applied."""
    applied: dict = {}
    defaults = _PROFILE_DEFAULTS.get(profile, {})
    for k, v in defaults.items():
        if k not in env:
            env[k] = v
            applied[k] = v
    return applied
```

(`resolve_profile` already lowercases env so `quick` resolves; no change there. Keep `FAST_DEFAULTS` intact — Task-1 of fast-mode tests still pass.)

- [ ] **Step 4: Run → PASS** (`-k quick` + the existing profile tests). 
- [ ] **Step 5: Commit:** `git -c commit.gpgsign=false add albert/profile.py tests/test_profile.py && git -c commit.gpgsign=false commit -m "feat(profile): quick profile defaults (minimal research, no debate round)"`

---

## Task 2: phase_0 query cap (`ALBERT_RESEARCH_MAX_QUERIES`)

**Files:** Modify `albert/phases/phase_0_intake_grounding.py`; Test `tests/test_research_max_queries.py`

- [ ] **Step 1: Failing test** `tests/test_research_max_queries.py`:

```python
import importlib
p0 = importlib.import_module("albert.phases.phase_0_intake_grounding")


def test_default_is_eight(monkeypatch):
    monkeypatch.delenv("ALBERT_RESEARCH_MAX_QUERIES", raising=False)
    assert p0._research_max_queries() == 8


def test_env_caps(monkeypatch):
    monkeypatch.setenv("ALBERT_RESEARCH_MAX_QUERIES", "3")
    assert p0._research_max_queries() == 3


def test_bad_value(monkeypatch):
    monkeypatch.setenv("ALBERT_RESEARCH_MAX_QUERIES", "x")
    assert p0._research_max_queries() == 8
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — add helper + use it in the default-path slice. Add:

```python
def _research_max_queries() -> int:
    try:
        return max(1, int(os.environ.get("ALBERT_RESEARCH_MAX_QUERIES", "8")))
    except (TypeError, ValueError):
        return 8
```

Change the default-path line `queries = (plan.get("queries") or [])[:8]` to:
```python
            queries = (plan.get("queries") or [])[:_research_max_queries()]
```

- [ ] **Step 4: Run → PASS.** Full suite green.
- [ ] **Step 5: Commit:** `git -c commit.gpgsign=false add albert/phases/phase_0_intake_grounding.py tests/test_research_max_queries.py && git -c commit.gpgsign=false commit -m "feat(phase0): ALBERT_RESEARCH_MAX_QUERIES cap (default 8; quick=3)"`

---

## Task 3: Extract `signals_apply.apply_signals` (DRY phase_4)

**Files:** Create `albert/signals_apply.py`; Modify `albert/phases/phase_4_signals_action_gate.py`; Test `tests/test_signals_apply.py`

- [ ] **Step 1: Failing test** `tests/test_signals_apply.py`:

```python
from albert.signals_apply import apply_signals


def test_apply_signals_sets_risk_action_verdict():
    state = {"research_state": {}}
    res = {"premature_end_atoms": {"open_high_impact_challenges": 3, "new_info_rate": "high"},
           "drift_atoms": {}, "proposed_next_action": "synthesize",
           "reproducible_judgment": "建議 synthesize。",
           "verdict_standalone": "要補證據", "light": "yellow", "readiness_score_delta": 0,
           "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []}}
    apply_signals(state, res)
    assert state["premature_end_risk"]["level"] == "high"
    assert state["premature_end_risk"]["why"]                    # non-empty (from why-builder)
    assert state["recommended_next_action"] == "continue_research"   # vetoed from synthesize
    assert "經訊號否決改為 continue_research" in state["reproducible_judgment"]
    assert state["verdict_standalone"] == "要補證據"
    assert state["light"] == "yellow"
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Create `albert/signals_apply.py`:**

```python
"""Deterministic signals/verdict application shared by phase_4 and phase_quick_combined.

Given an LLM result dict (atoms + proposed action + verdict-presentation fields),
compute the rule-grounded risk levels + vetoed action and write them into state.
No LLM call. Mirrors the contract phase_4 established."""
from __future__ import annotations

from albert.signals import (premature_end_level, drift_level, rank_next_probe,
                            build_risk, enforce_action_consistency,
                            premature_end_why, drift_why)

_STUB_PE = {"open_high_impact_challenges": 1, "new_info_rate": "unknown",
            "challenge_map_mostly_classified": False,
            "unresolved_are_human_data_decision_only": False,
            "meta_question_search_found_new_high_impact_angle": False}
_STUB_GATE = {"can_decide_now": [], "cannot_decide": [], "owners": []}


def apply_signals(state: dict, res: dict) -> None:
    rs = state.get("research_state") or {}
    pe_atoms = res.get("premature_end_atoms") or dict(_STUB_PE)
    dr_atoms = res.get("drift_atoms") or {}
    pe_level, dr_level = premature_end_level(pe_atoms), drift_level(dr_atoms)
    state["premature_end_risk"] = build_risk(pe_level, pe_atoms, rs, why=premature_end_why(pe_atoms))
    state["research_drift_risk"] = build_risk(dr_level, dr_atoms, rs, why=drift_why(dr_atoms))
    state["recommended_next_probe"] = rank_next_probe(res.get("recommended_next_probe") or [])
    state["missing_evidence"] = res.get("missing_evidence") or []
    state["questions_albert_would_ask"] = res.get("questions_albert_would_ask") or []
    _proposed = res.get("proposed_next_action", "continue_research")
    state["recommended_next_action"] = enforce_action_consistency(
        _proposed, pe_level, dr_level, state["missing_evidence"])
    state["rationale"] = res.get("rationale") or ""
    state["decision_gate"] = res.get("decision_gate") or dict(_STUB_GATE)
    _rj = res.get("reproducible_judgment") or ""
    if state["recommended_next_action"] != _proposed:
        _rj = (_rj + f"（註:LLM 原建議 {_proposed},經訊號否決改為 "
                     f"{state['recommended_next_action']}。）")
    state["reproducible_judgment"] = _rj
    state["verdict_standalone"] = res.get("verdict_standalone", "要補證據")
    state["light"] = res.get("light", "yellow")
    state["readiness_score_delta"] = int(res.get("readiness_score_delta", 0))
```

- [ ] **Step 4: Refactor phase_4** to use it. In `phase_4_signals_action_gate.py`, replace the deterministic tail (from `pe_atoms = ...` through `state["readiness_score_delta"] = ...`) with:
```python
    from albert.signals_apply import apply_signals
    apply_signals(state, res)
```
Keep everything else (the `call_claude`, the `_STUB` fallback assignment of `res`, `state["phase_4_status"]/_complete`, and the deliberation.block call — note the deliberation block reads `state["premature_end_risk"]` etc. which apply_signals set, so keep it AFTER the apply_signals call).

- [ ] **Step 5: Run** `py -3 -m pytest tests/test_signals_apply.py tests/test_veto_note.py -v` → PASS (the existing phase_4 veto-note test must still pass via the refactor). Full suite green.
- [ ] **Step 6: Commit:** `git -c commit.gpgsign=false add albert/signals_apply.py albert/phases/phase_4_signals_action_gate.py tests/test_signals_apply.py && git -c commit.gpgsign=false commit -m "refactor(signals): extract apply_signals shared by phase_4 + quick"`

---

## Task 4: `QUICK_COMBINED` schema + `quick_combined.txt` prompt

**Files:** Modify `albert/schemas.py`; Create `albert/prompts/quick_combined.txt`; Test `tests/test_quick_schema.py`

- [ ] **Step 1: Failing test** `tests/test_quick_schema.py`:

```python
from albert import schemas


def test_quick_combined_has_challenge_and_verdict_fields():
    props = schemas.QUICK_COMBINED["properties"]
    assert "albert_challenges" in props      # from CHALLENGE_GENERATION
    assert "top_ambiguities" in props
    assert "premature_end_atoms" in props    # from SIGNALS_VERDICT_MERGED
    assert "verdict_standalone" in props
    assert "proposed_next_action" in props
    assert schemas.QUICK_COMBINED["type"] == "object"
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — append to `albert/schemas.py`:

```python
# Quick mode: ONE call producing challenges + ambiguities + signals atoms + verdict.
QUICK_COMBINED = {
    "type": "object",
    "properties": {
        **CHALLENGE_GENERATION["properties"],
        **SIGNALS_VERDICT_MERGED["properties"],
    },
    "required": ["albert_challenges", "top_ambiguities",
                 "premature_end_atoms", "proposed_next_action",
                 "verdict_standalone", "light", "readiness_score_delta"],
}
```

- [ ] **Step 4: Create `albert/prompts/quick_combined.txt`:**

```
You are Albert in QUICK mode — a fast ~80%-quality pass. In ONE response, audit the CURRENT ANSWER:
1. The 3 most dangerous ambiguities (term / why_dangerous / precise_question).
2. Up to 6 high-impact 拷問 (albert_challenges) — each with challenge, why_albert_would_ask,
   status, severity, current_answer_strength, generator, bone, and evidence_refs ([Rk] ids from
   the Research section, ≤2, empty if none). For EACH challenge add a one-line inline
   self-critique inside why_albert_would_ask's spirit: is it sharp and research-backed? Keep prose tight.
3. weak_points, would_survive_leadership.
4. The signals atoms (premature_end_atoms, drift_atoms), recommended_next_probe, missing_evidence,
   questions_albert_would_ask, a proposed_next_action, rationale, decision_gate, reproducible_judgment.
5. The standalone verdict: verdict_standalone (可推進/要補證據/方向錯/產品定義不完整), light
   (green/yellow/red), readiness_score_delta (-2..2).
This is a single-pass quick review: be decisive and concise; do not pad. Emit StructuredOutput.
以繁體中文輸出。技術名詞(TC4, ASIL, Ethernet, AUTOSAR, gateway, MCU, zonal, OEM…)保留英文原文,不要硬翻。
```

- [ ] **Step 5: Run → PASS** (`tests/test_quick_schema.py`). 
- [ ] **Step 6: Commit:** `git -c commit.gpgsign=false add albert/schemas.py albert/prompts/quick_combined.txt tests/test_quick_schema.py && git -c commit.gpgsign=false commit -m "feat(quick): QUICK_COMBINED schema + quick_combined prompt"`

---

## Task 5: `phase_quick_combined` phase

**Files:** Create `albert/phases/phase_quick_combined.py`; Test `tests/test_phase_quick_combined.py`

- [ ] **Step 1: Failing test** `tests/test_phase_quick_combined.py`:

```python
from albert import deliberation
from albert.phases import phase_quick_combined as pq


def test_quick_phase_populates_contract(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    monkeypatch.setattr(pq, "call_claude", lambda **k: {
        "albert_challenges": [{"bone": 2, "challenge": "c", "why_albert_would_ask": "w",
                               "severity": "high", "current_answer_strength": "weak",
                               "generator": "winning", "status": "needs_bu_judgment",
                               "evidence_refs": ["R1"]}],
        "weak_points": ["wp"], "would_survive_leadership": False,
        "top_ambiguities": [{"term": "t", "why_dangerous": "d", "precise_question": "q"},
                            {"term": "t2", "why_dangerous": "d", "precise_question": "q"},
                            {"term": "t3", "why_dangerous": "d", "precise_question": "q"}],
        "premature_end_atoms": {"open_high_impact_challenges": 2, "new_info_rate": "high"},
        "drift_atoms": {}, "proposed_next_action": "continue_research",
        "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
        "reproducible_judgment": "j", "verdict_standalone": "要補證據",
        "light": "yellow", "readiness_score_delta": 0})
    state = {"current_answer": "x", "research_state": {}, "research": [],
             "albert_input": {"current_answer": "x", "mode": "standalone"}}
    out = pq.phase_quick_combined(state)
    assert out["albert_challenges"][0]["bone"] == 2
    assert out["verdict_standalone"] == "要補證據"
    assert out["premature_end_risk"]["level"] in ("low", "medium", "high")
    assert out["recommended_next_action"]
    assert out["verdict"] == "exhausted"
    assert out["phase_4_status"] == "passed"
    assert deliberation.emitted("phase_quick_combined")


def test_quick_phase_degraded_on_failure(tmp_path, monkeypatch):
    deliberation.init(tmp_path)
    def boom(**k): raise RuntimeError("llm down")
    monkeypatch.setattr(pq, "call_claude", boom)
    state = {"current_answer": "x", "research_state": {}, "research": [],
             "albert_input": {"current_answer": "x", "mode": "standalone"}}
    out = pq.phase_quick_combined(state)
    assert out["phase_4_status"] == "failed"
    assert deliberation.emitted("phase_quick_combined")
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Create `albert/phases/phase_quick_combined.py`:**

```python
"""Quick mode: ONE Opus call doing challenges + inline self-critique + signals + verdict,
then deterministic signals.py application. No separate debate/rework round (the ~80% cut)."""
import sys
from albert.errors import VisibilityContractError
from albert.sdk_client import call_claude
from albert.models import model_for_role
from albert.utils import load_prompt, research_refs
from albert import schemas, deliberation
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


def phase_quick_combined(state: dict) -> dict:
    ctx = (f"Output purpose: {state.get('output_purpose','')}\n\n"
           f"Current answer:\n{state.get('current_answer','')[:6000]}\n\n"
           f"Research (cite [Rk] in evidence_refs):\n{research_refs(state.get('research', []))}\n")
    status = "passed"
    try:
        res = call_claude(model=model_for_role("challenge_generation"),
                          system=load_prompt("albert_persona") + "\n\n" + load_prompt("quick_combined"),
                          user=ctx, json_schema=schemas.QUICK_COMBINED, purpose="quick_combined")
    except VisibilityContractError:
        raise
    except Exception as e:
        sys.stderr.write(f"[WARN] phase_quick failed: {type(e).__name__}: {str(e)[:200]}; stub\n")
        res, status = dict(_STUB), "failed"
    challenges = res.get("albert_challenges") or _STUB["albert_challenges"]
    state["albert_challenges"] = challenges
    state["weak_points"] = res.get("weak_points") or []
    state["missing_business_context"] = res.get("missing_business_context") or []
    state["would_survive_leadership"] = bool(res.get("would_survive_leadership", False))
    amb = res.get("top_ambiguities") or []
    if not isinstance(amb, list) or len(amb) < 3:
        amb = (amb if isinstance(amb, list) else []) + _STUB["top_ambiguities"]
    state["top_ambiguities"] = amb[:3]
    apply_signals(state, res)                       # risk/action/verdict from the same result
    state["verdict"] = "exhausted"                  # single pass, no rework
    state["phase_2_status"] = status
    state["phase_4_status"], state["phase_4_complete"] = status, True
    # deliberation: challenges + verdict in one block
    body = (deliberation.render_challenges(state)
            + "\n\n(quick 模式:單次審查 + inline 自我檢查,無多票辯論)\n\n"
            + deliberation.render_signals({
                "premature_end_risk": state["premature_end_risk"],
                "research_drift_risk": state["research_drift_risk"],
                "proposed_next_action": res.get("proposed_next_action", "?"),
                "recommended_next_action": state["recommended_next_action"]})
            + "\n\n" + deliberation.render_verdict({
                "verdict_standalone": state["verdict_standalone"], "light": state["light"],
                "readiness_score_delta": state["readiness_score_delta"],
                "recommended_next_action": state["recommended_next_action"],
                "reproducible_judgment": state["reproducible_judgment"]}))
    deliberation.block("phase_quick_combined", "PHASE Q ─ 快速審查(quick)", body)
    return state
```

- [ ] **Step 4: Run → PASS** (`tests/test_phase_quick_combined.py`, 2 tests). Full suite green.
- [ ] **Step 5: Commit:** `git -c commit.gpgsign=false add albert/phases/phase_quick_combined.py tests/test_phase_quick_combined.py && git -c commit.gpgsign=false commit -m "feat(quick): phase_quick_combined — one-call challenges+signals+verdict"`

---

## Task 6: Graph route + run_albert `--quick` (+ profile in state)

**Files:** Modify `albert/graph.py`, `run_albert.py`; Test `tests/test_quick_route.py`

- [ ] **Step 1: Failing test** `tests/test_quick_route.py`:

```python
from albert.graph import _route_after_intake


def test_route_quick():
    assert _route_after_intake({"profile": "quick"}) == "phase_quick_combined"


def test_route_default():
    assert _route_after_intake({"profile": "thorough"}) == "phase_2_challenge_generation"
    assert _route_after_intake({}) == "phase_2_challenge_generation"
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: graph.py** — add the import `from albert.phases.phase_quick_combined import phase_quick_combined`; add the routing fn:

```python
def _route_after_intake(state: dict) -> str:
    if state.get("profile") == "quick":
        return "phase_quick_combined"
    return "phase_2_challenge_generation"
```

In `build_graph`, add the node to the node list:
`("phase_quick_combined", phase_quick_combined),`. Replace `g.add_edge("phase_0_intake_grounding", "phase_2_challenge_generation")` with:
```python
    g.add_conditional_edges("phase_0_intake_grounding", _route_after_intake,
        {"phase_quick_combined": "phase_quick_combined",
         "phase_2_challenge_generation": "phase_2_challenge_generation"})
    g.add_edge("phase_quick_combined", "phase_5_assemble_render")
```

- [ ] **Step 4: run_albert.py** — add `--quick` flag (after `--fast`):
```python
    ap.add_argument("--quick", action="store_true")
```
Change the profile resolution block to handle quick + mutual exclusion (quick wins):
```python
    if args.quick:
        profile = "quick"
        if args.fast:
            sys.stderr.write("[profile] both --quick and --fast given; using quick\n")
    else:
        profile = resolve_profile(args.fast, os.environ)
    _applied = apply_profile(profile, os.environ)
    if profile in ("fast", "quick"):
        sys.stderr.write(f"[profile] {profile} — {', '.join(f'{k}={v}' for k, v in _applied.items()) or '(all pre-set)'}\n")
```
And put the profile into the initial state — find the `initial = {...}` dict in `main()` and add `"profile": profile,`. Pass `profile` to the banner call too (already `_deliberation_banner(run_dir, profile)`).

- [ ] **Step 5: Run** `py -3 -m pytest tests/test_quick_route.py -v` → PASS. Full suite green. Smoke: `py -3 run_albert.py "x" --quick --dry-run --allow-redirect` → prints `[profile] quick — ...` + dry-run line.

- [ ] **Step 6: Commit:** `git -c commit.gpgsign=false add albert/graph.py run_albert.py tests/test_quick_route.py && git -c commit.gpgsign=false commit -m "feat(quick): graph routes p0→quick→p5; --quick flag + profile in state"`

---

## Task 7: SKILL.md doc

**Files:** Modify `SKILL.md`

- [ ] **Step 1:** After the "Fast mode(`--fast`)" section add:

```markdown
## Quick mode(`--quick`)

最趕時間用 quick(目標 ~5 分鐘、品質 ~80 分):

    py -3 run_albert.py "<你的提案>" --quick

Quick **刻意砍品質換速度**:研究只查 3 條、**跳過多票自我辯論與重做**,把「拷問 + inline
自我檢查 + 裁決」併成一次 Opus 呼叫(`p0 → quick → 裁決`)。會少了 thorough/fast 的多票辯論
深度,適合快速一瞥,不適合正式決策。要完整審查用預設 thorough,要兼顧速度與品質用 `--fast`。
```

- [ ] **Step 2: Commit:** `git -c commit.gpgsign=false add SKILL.md && git -c commit.gpgsign=false commit -m "docs: document --quick (~5 min, ~80%) mode"`

---

## Task 8: Benchmark quick vs thorough/fast

**Files:** Modify `docs/speedup-results.md`

- [ ] **Step 1:** Run quick on the same bench proposal used before, foreground/background per the live rules, `--allow-redirect`:
`py -3 run_albert.py "<bench proposal>" --quick --allow-redirect` — capture wall-clock (`runs/<id>/progress.jsonl` last total_elapsed_sec) + verdict fields from `albert_challenge.json`.
- [ ] **Step 2:** Append a "## Quick mode (2026-06-03)" section to `docs/speedup-results.md`: wall-clock vs thorough (1082s) and fast (835s); ratio; the quality note (challenges present + verdict; **no multi-vote debate** — the intentional ~80%); state whether it met ≤6 min (aim 5). If >6 min, note the next cut (research 3→2, challenges cap 6→5).
- [ ] **Step 3: Commit:** `git -c commit.gpgsign=false add docs/speedup-results.md && git -c commit.gpgsign=false commit -m "docs(bench): quick mode wall-clock + ~80% quality note"`

---

## Self-Review

**1. Spec coverage:** quick profile+defaults (T1); research cap (T2); apply_signals DRY (T3); QUICK_COMBINED schema + prompt (T4); phase_quick_combined (T5); graph route + --quick + profile-in-state + mutual-exclusion (T6); SKILL.md (T7); benchmark (T8). Cockpit contract unchanged (quick sets all build_challenge fields incl. verdict/phase_4_status). ✓

**2. Placeholder scan:** none — all code complete. T5's `_STUB` + apply_signals defaults cover the degraded path.

**3. Type consistency:** `apply_profile`/`resolve_profile` (T1), `_research_max_queries` (T2), `apply_signals(state,res)` (T3 used by T5), `QUICK_COMBINED` (T4 used by T5), `phase_quick_combined` (T5 used by T6 graph), `_route_after_intake` (T6). `render_challenges/render_signals/render_verdict` reused with the same signatures from the deliberation module. quick sets `phase_2_status`+`phase_4_status` so phase_5's `_STATUS_KEYS` degraded-check works. ✓
