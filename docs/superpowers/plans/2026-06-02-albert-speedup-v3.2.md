# Albert Speedup v3.2 Implementation Plan — cut the 雞肋

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Cut two marginal processes (self-critique re-searching; ambiguity-hunt round-trip) plus a minor websearch trim, taking a run from ~11.4 min toward ~8.5 min with low quality impact and no paid infra.

**Architecture:** Pure-Python edits to the existing `albert/` LangGraph skill. Self-critique stops re-searching (judges from the research already in state); the ambiguity-hunt phase is folded into challenge-generation (one call) and dropped from the graph; websearch default turns 3→2. The deterministic rule engine, output contract, and exhaustion loop are untouched.

**Tech Stack:** Python 3, `claude_agent_sdk`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-06-02-albert-speedup-v3.2-trim-design.md`.
**Repo:** `D:\D-claude\skill-cn5-i-am-albert` (branch main; 123 tests pass). `py -3`; commit per task `git -c commit.gpgsign=false commit`.

---

## Task 1: Self-critique judges from existing research (no re-search)

**Files:** Modify `albert/phases/phase_3_self_critique_audit.py`, `albert/prompts/self_critique_auditor.txt`; Test `tests/test_phase_3_audit.py`.

- [ ] **Step 1: Failing test (assert no tools requested)**

```python
# tests/test_phase_3_audit.py  (add)
def test_votes_do_not_use_tools(monkeypatch):
    import albert.phases.phase_3_self_critique_audit as m
    captured = {}
    def fake(**k):
        captured["allow_tools"] = k.get("allow_tools")
        return {"round": 1, "verdict": "exhausted", "weaknesses": []}
    monkeypatch.setattr(m, "call_claude", fake)
    m.phase_3_self_critique_audit({"albert_challenges": [{"challenge": "x"}], "research": [{"query":"q","results":"r"}]})
    assert captured["allow_tools"] is False
```

- [ ] **Step 2: Run → FAIL** (currently `allow_tools=True`). `py -3 -m pytest tests/test_phase_3_audit.py::test_votes_do_not_use_tools -v`

- [ ] **Step 3: Edit `phase_3_self_critique_audit.py`** — in `_one_vote`:
  - change `allow_tools=True` → `allow_tools=False`, drop `max_turns=3` (use default).
  - prepend a research digest to the vote `user` payload so the auditor judges research-backedness from what's already gathered. The phase has `state["research"]`; pass a digest into `_one_vote`. Concretely, build once in `phase_3_self_critique_audit` before the fan-out:

```python
    research = state.get("research") or []
    digest = "\n".join(f"- {r.get('query','')}: {str(r.get('results',''))[:300]}" for r in research[:6])
    payload = json.dumps(state["albert_challenges"], ensure_ascii=False)[:20000]
    votes = parallel_run([(lambda v=v: _one_vote(v, payload, digest)) for v in range(1, NUM_VOTES + 1)])
```
  and in `_one_vote(v, payload, digest)`:

```python
    user = (f"Vote {v} of {NUM_VOTES}. Audit these challenges from a fresh, skeptical angle; "
            f"classify each weakness; give a verdict.\n\nChallenges:\n{payload}\n\n"
            f"Research already gathered (judge 'research-backed' against THIS, do not search):\n{digest}\n")
    a = call_claude(model=model_for_role("self_critique_audit"),
                    system=load_prompt("self_critique_auditor"),
                    json_schema=schemas.SELF_CRITIQUE_AUDIT, user=user,
                    allow_tools=False, timeout_sec=240, purpose=f"self_critique_audit_vote_{v}")
```

- [ ] **Step 4: Edit `self_critique_auditor.txt`** — replace any "Use WebSearch to check whether a challenge is research-backed" line with: "Judge whether each challenge is supported by the provided research findings; do NOT search the web."

- [ ] **Step 5: Run full suite → PASS** (the 3 existing phase_3 cases must still pass — they monkeypatch `call_claude`/`ClaudeSession`; ensure they pass the new `_one_vote` signature or patch at `call_claude`). `py -3 -m pytest tests/ -q`

- [ ] **Step 6: Commit** `perf: self-critique judges from existing research, no re-search (-80s)`.

---

## Task 2: Merge ambiguity-hunt into challenge generation

**Files:** Modify `albert/schemas.py`, `albert/phases/phase_2_challenge_generation.py`, `albert/prompts/challenge_generation.txt`, `albert/graph.py`; Test `tests/test_phase_2_challenge.py`, `tests/test_graph_topology.py`.

- [ ] **Step 1: Failing test (challenge call yields ambiguities; state populated)**

```python
# tests/test_phase_2_challenge.py  (add)
def _amb(t): return {"term": t, "why_dangerous": "w", "precise_question": "p"}
def test_phase_2_emits_top_ambiguities(monkeypatch):
    import albert.phases.phase_2_challenge_generation as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {
        "albert_challenges": [{"challenge": "c", "why_albert_would_ask": "y", "status": "blocked",
                               "severity": "high", "current_answer_strength": "weak",
                               "generator": "winning", "bone": 2}],
        "weak_points": [], "missing_business_context": [], "would_survive_leadership": False,
        "top_ambiguities": [_amb("a"), _amb("b"), _amb("c")]})
    out = m.phase_2_challenge_generation({"current_answer": "x", "research": [], "meta_question": {},
        "skeptic_output": [], "source_critic_output": [], "output_purpose": "x"})
    assert len(out["top_ambiguities"]) == 3
```

- [ ] **Step 2: Run → FAIL.** `py -3 -m pytest tests/test_phase_2_challenge.py::test_phase_2_emits_top_ambiguities -v`

- [ ] **Step 3: `albert/schemas.py`** — add `top_ambiguities` to `CHALLENGE_GENERATION["properties"]` (reuse the AMBIGUITY_HUNT item shape, exactly 3):

```python
CHALLENGE_GENERATION["properties"]["top_ambiguities"] = {
    "type": "array", "items": {"type": "object", "properties": {
        "term": {"type": "string"}, "why_dangerous": {"type": "string"},
        "precise_question": {"type": "string"}},
        "required": ["term", "why_dangerous", "precise_question"]},
    "minItems": 3, "maxItems": 3,
}
CHALLENGE_GENERATION["required"] = CHALLENGE_GENERATION["required"] + ["top_ambiguities"]
```

- [ ] **Step 4: `phase_2_challenge_generation.py`** — after the merge, write ambiguities to state with a defensive pad-to-3 (reuse Phase-1's stub):

```python
    def _amb_stub():
        return [{"term": "(LLM unavailable)", "why_dangerous": "review could not run",
                 "precise_question": "re-run Albert"} for _ in range(3)]
    amb = res.get("top_ambiguities") or []
    if not isinstance(amb, list) or len(amb) < 3:
        amb = (amb or []) + _amb_stub()
    state["top_ambiguities"] = amb[:3]
```
(In the fan-out merge variant, take `top_ambiguities` from the first non-stub generator result, or have only the `winning` generator emit them; simplest: the merged single-context already includes the instruction — collect `top_ambiguities` from whichever slice returns them, else stub.)

- [ ] **Step 5: `challenge_generation.txt`** — prepend: "FIRST surface the 3 most dangerous ambiguities (term / why_dangerous / precise_question) in the current answer, THEN the challenges. Return both in the structured output."

- [ ] **Step 6: `albert/graph.py`** — remove the `phase_1_ambiguity_hunt` node and its edges; add edge `phase_0_intake_grounding → phase_2_challenge_generation`. Leave `phase_1_ambiguity_hunt.py` on disk (unused) for possible later standalone use.

- [ ] **Step 7: Update `tests/test_graph_topology.py`** — assert `phase_1_ambiguity_hunt` is NOT a node; assert `phase_0 → phase_2` edge; exhaustion loop `phase_3 → phase_2` intact; no orphan.

- [ ] **Step 8: Run full suite → PASS.** Fix `test_phase_1_ambiguity.py` if it tested the now-unwired phase — keep it as a unit test of the (still-present) function, OR mark it skipped with a note. `py -3 -m pytest tests/ -q`

- [ ] **Step 9: Commit** `perf: merge ambiguity-hunt into challenge generation (-84s)`.

---

## Task 3: websearch default max_turns 3 → 2

**Files:** Modify `albert/sdk_client.py`; Test `tests/test_websearch_max_turns.py`.

- [ ] **Step 1: Edit test** — change the default-value assertion to 2:

```python
def test_default_max_turns(monkeypatch):
    monkeypatch.delenv("ALBERT_WEBSEARCH_MAX_TURNS", raising=False)
    assert sc._websearch_max_turns() == 2
```

- [ ] **Step 2: Run → FAIL** (default still 3).
- [ ] **Step 3: Edit `_websearch_max_turns`** default `"3"` → `"2"`.
- [ ] **Step 4: Run → PASS. Step 5: Commit** `perf: websearch default max_turns 2`.

---

## Task 4: Verify + re-benchmark

- [ ] **Step 1:** Full suite green: `py -3 -m pytest tests/ -q`.
- [ ] **Step 2:** Smoke: `py -3 run_albert.py --dry-run "x"` exit 0.
- [ ] **Step 3:** Real dogfood on `/tmp/albert_dogfood_proposal.txt`; record per-phase wall-clock (expect Phase 1 gone, Phase 3 ~40-50s) → total ~8.5 min; confirm quality parity (competitors named, centralized-vs-zonal catch, moat test, top_ambiguities still present + distinct, 🔴/Δ−2/would-not-survive).
- [ ] **Step 4: Commit** fixups; report measured time + quality delta.

---

## Self-Review
- **Spec coverage:** 2.1→Task1, 2.2→Task2, 2.3→Task3, verify→Task4. ✓
- **Placeholders:** all code shown; the fan-out ambiguity-collection note (Task 2 Step 4) gives the concrete rule (first non-stub slice / winning generator / stub). ✓
- **Type consistency:** `top_ambiguities` shape matches `AMBIGUITY_HUNT` items; `_one_vote(v, payload, digest)` signature consistent between caller and def; `_websearch_max_turns` default; graph edge `phase_0→phase_2`; consumers (`state["top_ambiguities"]`) unchanged. ✓
