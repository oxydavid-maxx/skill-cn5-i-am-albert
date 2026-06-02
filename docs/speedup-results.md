# Albert Speedup Results (2026-06-01 → 06-02)

All runs on the same proposal (CN5 Zonal Gateway SoC), measured wall-clock from
`runs/<id>/progress.jsonl`. **Quality held across every build** — same harsh judgment
(🔴 light / `readiness_delta = −2` / would-not-survive-leadership), same real competitors
named (S32G3 / R-Car / AURIX / TC4x), same 3 dangerous ambiguities + first-principles
catch (centralized-vs-zonal) + moat/durability test.

## Measured progression

| Build | Wall-clock | Levers added | Quality |
|---|---|---|---|
| Baseline | ~22 min (1320s) | fully sequential | reference |
| Parallelization | 939s ≈ **15.7 min** | parallel websearches + parallel self-critique votes | held |
| v3 | 682s ≈ **11.4 min** | + single-wave Phase 0, merge Phase 4+5, trim challenge verbosity | held |
| **v3.2 (current)** | 556s ≈ **9.3 min** | + self-critique judges from existing research (no re-search), merge ambiguity-hunt into challenge-gen, websearch `max_turns`=2 | held |

**Net: 22 → 9.3 min (−58%), quality maintained.**

## What worked
- **Parallelize small-output calls** (searches, votes) — bounded by the slowest, not the sum.
- **Collapse sequential stages** — single-wave Phase 0 (4 stages → 2), merge Phase 4+5 (one call), merge ambiguity into challenge-gen.
- **Cut redundant work** — self-critique stopped re-searching what Phase 0 already grounded (also removed 3-way search rate contention).

## What didn't / unavailable (tested honestly)
- **Fan-out of the large-output challenge call (6 parallel)** → 6 concurrent large Opus outputs blew the output-tokens-per-minute limit → 429 retry storm → *slower* (407s vs 156s). **Reverted.**
- **Sonnet 4.6 routing** → clean benchmark = 18.5 min (*slower* than Opus) + shallower grounding (2 competitors vs 4). On this OAuth subscription Sonnet is not faster for these TTFT/search-bound calls. **Dropped.**
- **Opus fast mode** (same weights, 2.5× output, quality-neutral) → unavailable on this OAuth subscription (`betas` are API-key-only; `--speed` crashes the CLI). The one lever that would reach 3-5 min — needs an API-key account.
- **Tavily/Brave fast search backend (C8)** → built + shipped (`albert/search_backends.py`, env `ALBERT_SEARCH_BACKEND`), inert without a paid API key. Would cut each search ~150s → ~1-3s (Phase 0 ~216s → ~50s). Not pursued (paid).
- **Prompt caching** → auto-engages on this subscription (POC saw cache_creation→cache_read tokens); free cost/TTFT win on repeated prefixes, no wiring needed.

## The floor (~9 min)
Bounded by **(a) the agentic websearch (~150s/wave, model-independent)** and **(b) the chain of
sequential Opus calls (~60-130s each)**. Below ~9 min requires either paid infrastructure
(fast mode for a quality-neutral 2.5×, or a search API to kill the 150s search) or soul-touching
quality tradeoffs (shorter challenges, `max_turns`=1, fewer searches). Decision (2026-06-02):
accept ~9 min as the free-tier floor; speed work complete.

## Toggles (all default to the safe/quality path)
- `ALBERT_SEARCH_BACKEND=tavily|brave` (+ `TAVILY_API_KEY`/`BRAVE_API_KEY`) → fast search if a key is set.
- `ALBERT_FAST_MODE=1` → fast-mode beta (no-op on OAuth; engages on an API-key transport).
- `ALBERT_WEBSEARCH_MAX_TURNS` (default 2) · `ALBERT_MAX_REWORK` (default 2) · `ALBERT_RESEARCH_REFLECT=1` (restore the deeper 2-wave research).
