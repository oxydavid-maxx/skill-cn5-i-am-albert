# Albert Speedup v3 — Quality-Neutral Round-Trip & Cache Reduction

- **Skill:** `skill-cn5-i-am-albert`
- **Date:** 2026-06-02
- **Status:** design (A near-neutral levers + B4 trim + **C8 pluggable fast search**; target ~12.5 → ~6-7 min)
- **Builds on:** v2 parallelization (22→15.7 min) + single-wave Phase-0 collapse (→~12.5 min).
- **Excludes (empirically failed / unavailable, see v2 + dogfood):** Sonnet routing (no speedup on
  this OAuth subscription, reverted), phase-2 fan-out (rate-limit retry storm, reverted), fast mode
  (betas API-key-only; `--speed` crashes CLI — unavailable here).

## 1. Where the time is now (measured, parallelization + single-wave build)

P0 ~243s (intake + 1 parallel wave) · P1 79s · P2 156s · P3 126s · P4 107s · P5 38s ≈ **~12.5 min**.
Floor = (a) websearch latency (~150s per search, the single biggest cost) + (b) the chain of
sequential Opus calls (~60-130s each). v3 attacks the sequential-call count and per-search cost
without touching the soul or the model.

## 2. Changes

### 2.1 Merge Phase 4 + Phase 5 into one call (quality-neutral)
Phase 4 (signals-atom extraction, 107s) and Phase 5's LLM call (verdict/light render, part of 38s)
are two sequential round-trips that both just read the challenges and emit structured fields. Merge
into ONE call returning: `premature_end_atoms` + `drift_atoms` + `recommended_next_probe` +
`missing_evidence` + `questions_albert_would_ask` + `proposed_next_action` + `decision_gate` +
`reproducible_judgment` + `verdict_standalone` + `light` + `readiness_score_delta`.
- `signals.py` still computes the risk **levels** and **vetoes** the action deterministically (no
  change to the rule engine); the merged call only supplies atoms + the standalone presentation fields.
- Assembly, degraded guard, render stay in code (no LLM).
- Standard latency technique: "combine sequential steps into one prompt to avoid round-trip latency"
  ([OpenAI latency guide](https://developers.openai.com/api/docs/guides/latency-optimization)).
- **Saves ~60-80s** (one fewer Opus round-trip). Quality-neutral (same information, one synthesis).
- FSM: the verdict LLM call moves from `phase_5_assemble_render` into `phase_4_signals_action_gate`;
  phase_5 becomes pure assembly/render/email (no LLM). A merged StructuredOutput schema =
  `SIGNALS_ACTION_GATE` ∪ `VERDICT` fields.

### 2.2 Faster websearch (low quality risk)
Each `websearch` is an agentic SDK subprocess (WebSearch tool + LLM summary) with `max_turns=5`,
~150s — the single largest cost and the Phase-0 wave-wall bound. Add env `ALBERT_WEBSEARCH_MAX_TURNS`
(default **3**) and cap the summary instruction length in `_websearch_once`.
- Fewer tool turns → each search returns faster → the parallel wave's wall (= slowest search) shrinks.
- **Saves ~40-80s** on Phase 0. Mild quality risk: less per-query refinement; the parallel breadth
  (multiple queries) compensates. Env-tunable so depth can be restored.

### 2.3 Prompt caching (cost + TTFT; POC-gated)
Every phase resends a large fixed system prompt (the 12-bone persona + per-phase instructions).
Mark the static system prefix cacheable via Anthropic `cache_control` so it's processed once and
reused across calls.
- Reported effect: cache reads 0.1× input price, **TTFT improvement 13-31%** (40-60% on large
  system prompts), 80-95% hit rate for stable system prompts
  ([Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)).
- **POC-gated like fast mode:** caching may be API-key-gated on this OAuth subscription.
  `poc/prompt_cache_probe.py` issues two calls with a large cached system prefix and checks the
  usage block for `cache_creation_input_tokens` / `cache_read_input_tokens` > 0. If caching does
  NOT engage, skip this change (env `ALBERT_PROMPT_CACHE`, default off until POC green).
- Primarily a **cost** win + modest TTFT; quality completely neutral (same prompt, cached).

### 2.4 (optional, quality-POSITIVE) Trim challenge output verbosity
Phase 2 challenge-gen is output-bound (29.5K chars / 156s). Bound `meeting_ready_response` and
`recommended_probe` to 1 sentence each, `evidence_refs` to ≤2 — the **challenge body, why, status,
severity, missing_info are unchanged** (the soul). Output roughly halves.
- **Saves ~60-70s** AND improves usability (29.5K chars is too verbose to act on; tighter =
  signal-dense). Near-neutral-to-positive on quality.
- One-line instruction in `challenge_generation.txt`; no schema change (fields stay, just shorter).

### 2.5 Pluggable fast search backend (C8 — attacks the ~150s search floor)
Today `websearch()` spawns a full agentic Claude subprocess (WebSearch tool + LLM summary,
~150s) per query — the single largest cost in the whole run. Replace it with a **pluggable
search backend** (matches consumer PRODUCT-SPEC §16 "research worker should be replaceable"):

- Abstract `websearch(query)` behind a backend selected by env `ALBERT_SEARCH_BACKEND`:
  - `agentic` (current; high-quality, ~150s) — **stays the default** until the fast backend is proven.
  - `tavily` (**recommended fast**) — LLM-native search API: one HTTP call returns reranked,
    LLM-ready passages + source URLs in ~1-2s, no separate summary needed (~$0.008/query).
  - `brave` (fastest/cheapest) — 669ms latency, independent index, cheapest; returns SERP
    snippets (~200 words) which we pass through as the result string.
  ([Tavily/Brave/Serper comparison](https://aimultiple.com/agentic-search), [Brave Search API](https://brave.com/search/api/))
- Each backend returns the SAME shape as today: `{query, results, timestamp[, error]}`. The
  fast backends fill `results` with the API's passages/snippets. `websearch()` stays
  never-raises (degrade to error-tagged result), so the rest of the pipeline is unchanged.
- **POC-gated:** needs an API key (`TAVILY_API_KEY` / `BRAVE_API_KEY`). `poc/search_backend_probe.py`
  issues one query per available backend, prints latency + a result excerpt, and confirms the key
  works + the content is usable for grounding. If no key is available, the fast backends are
  inert and `agentic` remains.
- **Effect: ~150s/search → ~1-3s** → Phase-0 wave wall ~185s → ~5s (Phase 0 ~243s → ~50s, just the
  intake Opus call). **Quality tradeoff:** API passages are shallower than the agentic tool's
  multi-turn refinement — mitigated by the breadth of parallel queries and that Albert only needs
  grounding facts (competitor names, roadmap, standards), not deep synthesis. Default stays
  `agentic` so the high-quality path is never lost; `tavily` is the opt-in fast path.

## 3. Expected effect

| Change | Δ | Quality |
|---|---|---|
| 2.1 merge P4+P5 | −60-80s | neutral |
| 2.2 faster websearch (max_turns) | −40-80s | mild risk (env-tunable) |
| 2.3 prompt caching | cost + small TTFT | neutral (POC-gated) |
| 2.4 trim verbosity | −60-70s | positive (concision) |
| 2.5 fast search backend (C8) | **−~190s** (P0 243→~50s) | tradeoff (default-off; opt-in) |

**Projected:**
- 2.1 + 2.2 + 2.4 (no C8): ~12.5 → **~9-10 min**.
- **+ 2.5 C8 (tavily):** Phase 0 collapses to ~50s → **~6-7 min** — the residual floor is then the
  sequential Opus call chain (intake / challenge / self-critique / merged-signals, ~60-130s each).
- **3-5 min still needs faster Opus** (fast mode, unavailable here) OR merging more Opus phases
  (e.g. ambiguity into challenge-gen — a further quality tradeoff). C8 gets closest by killing the
  search floor; the Opus chain is the remaining wall.

## 4. Testing
- `tests/test_phase_4_signals.py` / `test_phase_5_assemble.py` — merged-call shape; `signals.py`
  still computes levels + vetoes action; degraded guard intact; phase_5 has no LLM call.
- `tests/test_graph_topology.py` — phase_5 still wired; no orphan.
- `tests/test_websearch_max_turns.py` — `ALBERT_WEBSEARCH_MAX_TURNS` flows into the websearch call
  options (assert on built options, no live call); default 3.
- `tests/test_prompt_cache_wiring.py` — when `ALBERT_PROMPT_CACHE=1`, system prefix carries
  `cache_control`; off → it doesn't (assert option dict).
- POC scripts (`poc/prompt_cache_probe.py`) are run-once gates, not unit tests.

## 5. Risks / open
- **Prompt caching availability** — POC-gated; may be OAuth-restricted like fast mode. If so, drop 2.3.
- **websearch max_turns** — too low (1) may starve a search; default 3 is the conservative knob.
- **Merge P4+P5** — the merged prompt is longer; ensure the merged StructuredOutput schema covers
  all fields (`SIGNALS_ACTION_GATE` ∪ `VERDICT`).
- **C8 search backend** — needs an API key (Tavily/Brave) + per-query cost; default stays `agentic`
  so the run never breaks without a key. Quality tradeoff (shallower passages) is the reason it's
  opt-in, not default. POC confirms key + content usability before any default change.
