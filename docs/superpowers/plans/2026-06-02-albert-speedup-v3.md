# Albert Speedup v3 Implementation Plan (A + B4 + C8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Cut a full Albert run from ~12.5 min toward ~6-7 min with no soul/model change: merge the signals+verdict round-trip, speed each websearch, add prompt caching, trim challenge verbosity, and add a pluggable fast search backend (Tavily/Brave) that kills the ~150s/search floor.

**Architecture:** Pure-Python edits to the existing `albert/` LangGraph skill. Two uncertain levers (prompt caching, fast search backend) are POC-gated and env-default-OFF so the run never breaks without an API key. The deterministic rule engine (`signals.py`) and output contract are untouched.

**Tech Stack:** Python 3, `claude_agent_sdk`, `tenacity`, `pytest`, `httpx`/`requests` (for the search-API backends).

**Spec:** `docs/superpowers/specs/2026-06-02-albert-speedup-v3-design.md`.
**Repo:** `D:\D-claude\skill-cn5-i-am-albert` (branch main; 92 tests pass). `py -3`; commit per task `git -c commit.gpgsign=false commit`.

---

## File map
- `albert/schemas.py` — add `SIGNALS_VERDICT_MERGED` (Task 1).
- `albert/phases/phase_4_signals_action_gate.py` — emit verdict fields too (Task 1).
- `albert/phases/phase_5_assemble_render.py` — drop the LLM call; pure assemble/guard/render/email (Task 1).
- `albert/prompts/signals_action_gate.txt` — fold in verdict instructions (Task 1).
- `albert/sdk_client.py` — `ALBERT_WEBSEARCH_MAX_TURNS` (Task 2); prompt-cache wiring (Task 3); pluggable `websearch` backend (Task 5).
- `albert/prompts/challenge_generation.txt` — brevity instruction (Task 4).
- `albert/search_backends.py` — NEW: `agentic` / `tavily` / `brave` (Task 5).
- `poc/prompt_cache_probe.py`, `poc/search_backend_probe.py` — NEW run-once gates (Tasks 3, 5).
- tests as named per task.

---

## Task 1: Merge Phase 4 + Phase 5 (one LLM call)

**Files:** Modify `albert/schemas.py`, `albert/phases/phase_4_signals_action_gate.py`, `albert/phases/phase_5_assemble_render.py`, `albert/prompts/signals_action_gate.txt`; Test `tests/test_phase_4_signals.py`, `tests/test_phase_5_assemble.py`.

- [ ] **Step 1: Failing test (phase 4 now also yields verdict fields)**

```python
# tests/test_phase_4_signals.py  (add)
def test_phase_4_emits_verdict_fields(monkeypatch):
    import albert.phases.phase_4_signals_action_gate as m
    monkeypatch.setattr(m, "call_claude", lambda **k: {
        "premature_end_atoms": {"open_high_impact_challenges": 0, "new_info_rate": "low"},
        "drift_atoms": {}, "recommended_next_probe": [], "missing_evidence": [],
        "questions_albert_would_ask": [], "proposed_next_action": "pull_human", "rationale": "r",
        "decision_gate": {"can_decide_now": [], "cannot_decide": [], "owners": []},
        "reproducible_judgment": "rj",
        "verdict_standalone": "要補證據", "light": "yellow", "readiness_score_delta": -1})
    out = m.phase_4_signals_action_gate({"current_answer": "x", "albert_challenges": [], "research_state": {}})
    assert out["verdict_standalone"] == "要補證據"
    assert out["light"] == "yellow"
    assert out["readiness_score_delta"] == -1
    assert out["recommended_next_action"]  # signals.py still vetoes/sets it
```

- [ ] **Step 2: Run → FAIL.** `py -3 -m pytest tests/test_phase_4_signals.py::test_phase_4_emits_verdict_fields -v`

- [ ] **Step 3: Add merged schema in `albert/schemas.py`** (union of SIGNALS_ACTION_GATE + the 3 verdict fields):

```python
SIGNALS_VERDICT_MERGED = {
    "type": "object",
    "properties": {
        **SIGNALS_ACTION_GATE["properties"],
        "verdict_standalone": {"type": "string", "enum": ["可推進", "要補證據", "方向錯", "產品定義不完整"]},
        "light": {"type": "string", "enum": ["green", "yellow", "red"]},
        "readiness_score_delta": {"type": "integer", "minimum": -2, "maximum": 2},
    },
    "required": SIGNALS_ACTION_GATE["required"] + ["verdict_standalone", "light", "readiness_score_delta"],
}
```

- [ ] **Step 4: `phase_4_signals_action_gate.py`** — use `schemas.SIGNALS_VERDICT_MERGED`; after computing signals + `recommended_next_action`, also persist the verdict fields:

```python
    res = call_claude(model=model_for_role("signals_action_gate"),
                      system=load_prompt("signals_action_gate"), user=ctx,
                      json_schema=schemas.SIGNALS_VERDICT_MERGED, purpose="signals_action_gate")
    # ... existing signals + enforce_action_consistency ...
    state["verdict_standalone"] = res.get("verdict_standalone", "要補證據")
    state["light"] = res.get("light", "yellow")
    state["readiness_score_delta"] = int(res.get("readiness_score_delta", 0))
```
(Keep the stub fallback returning these too: add `verdict_standalone="產品定義不完整", light="red", readiness_score_delta=-2` to `_STUB`.)

- [ ] **Step 5: `phase_5_assemble_render.py`** — delete the `call_claude(verdict_render...)` block. Compute `degraded`/`run_status` from phase statuses (unchanged), read `verdict_standalone`/`light`/`readiness_score_delta` from `state` (set by phase 4), apply `enforce_degraded_guard` (unchanged), then `write_challenge_json` + `write_report` + email. No LLM call remains in phase 5.

- [ ] **Step 6: Prompt** — append the `verdict_render.txt` instructions into `albert/prompts/signals_action_gate.txt` (choose `verdict_standalone` enum + `light` + `readiness_score_delta` in the SAME structured output). Keep "report atoms only; the system computes risk levels + vetoes the action".

- [ ] **Step 7: Update `tests/test_phase_5_assemble.py`** — phase 5 no longer calls `call_claude` (remove that monkeypatch; assert no LLM call). Seed `state["verdict_standalone"]/["light"]/["readiness_score_delta"]` as if phase 4 set them; assert degraded guard still downgrades green→red on a failed run; assert challenge_json + report written.

- [ ] **Step 8: Run full suite → PASS.** `py -3 -m pytest tests/ -q`
- [ ] **Step 9: Commit** `perf: merge phase 4+5 into one LLM call (signals+verdict)`.

---

## Task 2: Faster websearch (`ALBERT_WEBSEARCH_MAX_TURNS`)

**Files:** Modify `albert/sdk_client.py`; Test `tests/test_websearch_max_turns.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_websearch_max_turns.py
import albert.sdk_client as sc
def test_default_max_turns(monkeypatch):
    monkeypatch.delenv("ALBERT_WEBSEARCH_MAX_TURNS", raising=False)
    assert sc._websearch_max_turns() == 3
def test_env_override(monkeypatch):
    monkeypatch.setenv("ALBERT_WEBSEARCH_MAX_TURNS", "2")
    assert sc._websearch_max_turns() == 2
def test_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("ALBERT_WEBSEARCH_MAX_TURNS", "xx")
    assert sc._websearch_max_turns() == 3
```

- [ ] **Step 2: Run → FAIL** (`_websearch_max_turns` not defined).
- [ ] **Step 3: Implement in `albert/sdk_client.py`**

```python
def _websearch_max_turns() -> int:
    try:
        return max(1, int(os.environ.get("ALBERT_WEBSEARCH_MAX_TURNS", "3")))
    except (TypeError, ValueError):
        return 3
```
In `_websearch_once`, change the `ClaudeAgentOptions(... max_turns=5 ...)` to `max_turns=_websearch_max_turns()`.

- [ ] **Step 4: Run → PASS. Step 5: Commit** `perf: env-tunable websearch max_turns (default 3)`.

---

## Task 3: Prompt caching (POC-gated)

**Files:** Create `poc/prompt_cache_probe.py`; Modify `albert/sdk_client.py`; Test `tests/test_prompt_cache_wiring.py`.

- [ ] **Step 1: POC FIRST.** Create `poc/prompt_cache_probe.py` that builds a ~2K-token static system prompt, issues two `call_claude` calls with cache wiring, and prints the usage block looking for `cache_creation_input_tokens` / `cache_read_input_tokens`. Cache wiring attempt: pass `extra_args`/`betas`/a `cache_control` block per the SDK surface — the SDK `ClaudeAgentOptions` may not expose `cache_control` directly (system_prompt is a plain string), so the probe must also try `betas=["prompt-caching-..."]` if needed and REPORT whether any cache tokens appear. RUN it (`py -3 poc/prompt_cache_probe.py`). **If no cache tokens appear (OAuth-gated, like fast mode), STOP this task** — record the finding and leave caching env-default-OFF.

- [ ] **Step 2: Wiring (only if POC green).** Add `_prompt_cache_enabled()` (env `ALBERT_PROMPT_CACHE`, default "0"); when enabled, attach the cache directive the POC confirmed in `_sdk_query`/`ClaudeSession._build_options`.

- [ ] **Step 3: Test** `tests/test_prompt_cache_wiring.py`: when `ALBERT_PROMPT_CACHE=1`, built options carry the cache directive; when "0", they don't (assert option dict; no live call). If POC was red, this test asserts the default-off behavior only.

- [ ] **Step 4: Run → PASS. Step 5: Commit** `perf: prompt caching wiring (POC-gated, env ALBERT_PROMPT_CACHE)` (commit body records the POC result).

---

## Task 4: Trim challenge output verbosity (quality-positive)

**Files:** Modify `albert/prompts/challenge_generation.txt`; Test `tests/test_prompts_present.py`.

- [ ] **Step 1: Failing test (add to `tests/test_prompts_present.py`)**

```python
def test_challenge_prompt_demands_concise_fields():
    t = load_prompt("challenge_generation").lower()
    assert "1-2 sentence" in t or "one sentence" in t or "concise" in t
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Edit `albert/prompts/challenge_generation.txt`** — add a line: `"Keep meeting_ready_response and recommended_probe to ONE sentence each, evidence_refs to at most 2. The challenge, why_albert_would_ask, status, severity, current_answer_strength, missing_info stay full — only trim the supporting prose."`
- [ ] **Step 4: Run → PASS. Step 5: Commit** `perf: trim challenge supporting-prose verbosity (soul unchanged)`.

---

## Task 5: Pluggable fast search backend (C8)

**Files:** Create `albert/search_backends.py`, `poc/search_backend_probe.py`; Modify `albert/sdk_client.py` (`websearch` dispatch); Test `tests/test_search_backends.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_search_backends.py
import albert.search_backends as sb
def test_backend_selection_default(monkeypatch):
    monkeypatch.delenv("ALBERT_SEARCH_BACKEND", raising=False)
    assert sb.selected_backend() == "agentic"
def test_backend_selection_env(monkeypatch):
    monkeypatch.setenv("ALBERT_SEARCH_BACKEND", "tavily")
    assert sb.selected_backend() == "tavily"
def test_tavily_shape(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setattr(sb, "_http_post_json", lambda url, payload, headers, timeout:
                        {"results": [{"title": "T", "url": "u", "content": "passage"}], "answer": "ans"})
    r = sb.tavily_search("zonal gateway competitors")
    assert r["query"] == "zonal gateway competitors"
    assert "passage" in r["results"] and "u" in r["results"]
    assert "timestamp" in r
def test_tavily_missing_key_degrades(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    r = sb.tavily_search("q")
    assert r.get("error")  # never raises; degrades
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `albert/search_backends.py`**

```python
"""Pluggable search backends. Each returns {query, results, timestamp[, error]} —
the same shape as the agentic websearch — and NEVER raises (degrades to error-tagged)."""
import os, time, json, urllib.request

def selected_backend() -> str:
    return (os.environ.get("ALBERT_SEARCH_BACKEND") or "agentic").strip().lower()

def _http_post_json(url, payload, headers, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def tavily_search(query: str) -> dict:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return {"query": query, "results": "", "error": "TAVILY_API_KEY unset", "timestamp": time.time()}
    try:
        data = _http_post_json("https://api.tavily.com/search",
            {"api_key": key, "query": query, "search_depth": "basic",
             "include_answer": True, "max_results": 5}, {})
        parts = []
        if data.get("answer"):
            parts.append(data["answer"])
        for r in data.get("results", []):
            parts.append(f"- {r.get('title','')} ({r.get('url','')}): {str(r.get('content',''))[:400]}")
        return {"query": query, "results": "\n".join(parts), "timestamp": time.time()}
    except Exception as e:
        return {"query": query, "results": "", "error": f"{type(e).__name__}: {str(e)[:200]}", "timestamp": time.time()}

def brave_search(query: str) -> dict:
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        return {"query": query, "results": "", "error": "BRAVE_API_KEY unset", "timestamp": time.time()}
    try:
        import urllib.parse
        url = "https://api.search.brave.com/res/v1/web/search?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": key})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = [f"- {w.get('title','')} ({w.get('url','')}): {str(w.get('description',''))[:300]}"
                 for w in (data.get("web", {}) or {}).get("results", [])[:5]]
        return {"query": query, "results": "\n".join(parts), "timestamp": time.time()}
    except Exception as e:
        return {"query": query, "results": "", "error": f"{type(e).__name__}: {str(e)[:200]}", "timestamp": time.time()}
```

- [ ] **Step 4: Dispatch in `albert/sdk_client.py`** — at the top of `websearch(query_text, ...)`, route by backend before the agentic path:

```python
def websearch(query_text, max_tokens=4000):
    from albert import search_backends as _sb
    backend = _sb.selected_backend()
    if backend == "tavily":
        return _sb.tavily_search(query_text)
    if backend == "brave":
        return _sb.brave_search(query_text)
    # backend == "agentic": existing implementation below (unchanged)
    ...
```

- [ ] **Step 5: POC** `poc/search_backend_probe.py` — for each backend whose key is present, run one query, print latency + a result excerpt; confirm content is usable for grounding. RUN it. Record which backend(s) are available + their latency in the commit body.

- [ ] **Step 6: Run full suite → PASS.** `py -3 -m pytest tests/ -q`
- [ ] **Step 7: Commit** `feat: pluggable fast search backend (tavily/brave), agentic default (C8)`.

---

## Task 6: Verify + re-dogfood

- [ ] **Step 1:** Full suite green: `py -3 -m pytest tests/ -q`.
- [ ] **Step 2:** Smoke: `py -3 run_albert.py --dry-run "x"` exit 0.
- [ ] **Step 3:** If a search backend key is available, run a real dogfood with `ALBERT_SEARCH_BACKEND=tavily` on `/tmp/albert_dogfood_proposal.txt`; record wall-clock per phase + confirm the output still names real competitors, keeps the centralized-vs-zonal catch, moat test, and a harsh red verdict (quality parity vs the agentic baseline). If no key, run with `agentic` to confirm the merge/trim changes didn't regress, and note C8 needs a key to measure.
- [ ] **Step 4: Commit** any fixups; report measured time + quality delta.

---

## Self-Review
- **Spec coverage:** 2.1→Task1, 2.2→Task2, 2.3→Task3, 2.4→Task4, 2.5(C8)→Task5, verify→Task6. ✓
- **Placeholders:** POC steps describe exact checks (cache tokens / latency); search code is complete; caching wiring is POC-conditional by design (the uncertain SDK surface is resolved by the POC, not guessed). ✓
- **Type consistency:** `SIGNALS_VERDICT_MERGED` used in Task 1; `selected_backend`/`tavily_search`/`brave_search`/`_http_post_json` names consistent across Task 5 code + tests; `_websearch_max_turns` Task 2. Search backends return the exact `{query, results, timestamp[, error]}` shape `websearch` already produces, so phases are unchanged. ✓
