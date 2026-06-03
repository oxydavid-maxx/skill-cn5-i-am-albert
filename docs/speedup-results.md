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

## Fast mode A/B (2026-06-03) — research-preserving `--fast`

Same proposal (CN5 Gateway-MCU winning thesis), back-to-back, `--allow-redirect` (harness is
non-TTY). Fast profile = `ALBERT_MAX_REWORK=0`, `ALBERT_WEBSEARCH_MAX_TURNS=3`,
`ALBERT_RESEARCH_WIDTH=5` (research breadth — all 8 queries — unchanged).

| Run | Wall-clock | phase_0 (research) | standalone verdict | light | Δ | action | #challenges | #weak | evidence_refs |
|---|---|---|---|---|---|---|---|---|---|
| thorough (default) | 1081.8s (18.0 min) | 386.3s | 要補證據 | red | −1 | pull_human | 9 | 10 | 8/9 |
| **fast** (`--fast`) | **834.9s (13.9 min)** | 296.0s | 要補證據 | red | −1 | pull_human | 9 | 10 | 8/9 |
| **ratio** | **0.77×** | 0.77× | identical | = | = | = | = | = | = |

**Quality: parity (≈100%, well above the 90% floor).** Identical user-facing standalone verdict,
light, readiness delta, recommended action; same challenge/weak-point counts; same evidence_refs
coverage. (The internal `verdict` enum differed — thorough `continue`, fast `rework` — but fast's
`MAX_REWORK=0` correctly did not loop, and the decision-relevant outputs are identical.)

**Time: 0.77× this run (−23%), NOT the ≤0.55 target — honestly explained:** the thorough baseline
did **not** trigger a rework this run, so fast's biggest lever (no-rework) saved nothing here; the
saving came only from faster + wider search (phase_0 386s → 296s, breadth kept). The no-rework
lever pays off only when the baseline *would* rework — in earlier runs this session thorough
reworked and added a full phase-2+phase-3 cycle (~4-6 min), where fast would land ≈0.5×.

**So fast mode's speedup is conditional:**
- Baseline reworks (common on weaker/ambiguous proposals) → fast ≈ 0.5× (hits target).
- Baseline single-passes (like this run) → fast ≈ 0.75× (faster, but not half).
- A search-backend key (`ALBERT_SEARCH_BACKEND` + key) takes any case well under 0.5× (search
  150s → ~2s); the wiring is already present, inert without a key.

**Recommendation:** ship `--fast` as-is (parity quality, reliably faster, ≥0.5× when it matters
most — the rework case). If guaranteed half-time on single-pass proposals is required, the next
lever is either a paid search backend or a separate `--faster` that also trims research breadth
(explicitly declined for `--fast`, which is research-preserving by design).

## Quick mode A/B (2026-06-03) — `--quick` (~80% quality, target ≤6 min)

Same proposal. `quick` collapses the graph to `p0 → phase_quick_combined → p5` — ONE Opus call
(challenges + inline self-critique + signals + verdict), **skipping the 3-vote debate (p3) and
the separate signals round (p4)**. Knobs: MAX_REWORK=0, WEBSEARCH_MAX_TURNS=3, RESEARCH_WIDTH=3,
RESEARCH_MAX_QUERIES=3.

| Run | Wall-clock | graph nodes | standalone | light | Δ | #challenges | evidence_refs |
|---|---|---|---|---|---|---|---|
| thorough | 1081.8s (18.0m) | p0·p2·p3·p4·p5 | 要補證據 | red | −1 | 9 | 8/9 |
| fast | 834.9s (13.9m) | p0·p2·p3·p4·p5 | 要補證據 | red | −1 | 9 | 8/9 |
| **quick** | **358.8s (6.0m)** | **p0·quick·p5** | (要補/可推進級) | yellow | 0 | 6 | 4/6 |
| **quick ratio** | **0.33× thorough · 0.43× fast** | | | | | | |

**Time: hit the ≤6-min target (5.98 min); aim-5 missed.** Breakdown: phase_0 research ~197s
(the agentic-search floor, even at 3 queries) + the single combined call ~160s + render. To reach
5 min would need research cut to ~2 queries or a fast search backend key.

**Quality ~80% as designed:** a real audit (6 capped challenges + inline self-critique + verdict),
but **no multi-vote exhaustion debate, no rework, thinner research** (3 queries) — lighter judgment
(🟡 vs the thorough/fast 🔴 on this proposal). Fine for a quick look; use thorough for real decisions.

**Bug found & fixed by this benchmark:** the first quick runs silently executed the FULL thorough
pipeline. Root cause: LangGraph filters state to keys declared in `AlbertState`; `profile` wasn't
declared, so it was dropped and `_route_after_intake` always fell back to thorough. Unit tests
passed because they call the router directly (bypassing the state filter). Fix: declare
`profile` in `AlbertState` + a regression test (`tests/test_quick_route_integration.py`) that
filters an initial dict to the schema keys before routing. (Stale `.pyc` masked the fix on two
re-runs; verified with `PYTHONDONTWRITEBYTECODE=1`.)

**Cosmetic (fixed):** the reused renderers now take `header=False`; quick/flash blocks show one
profile banner (PHASE Q / PHASE F), not the misleading "PHASE 2/4/5" sub-headers.

## Flash mode A/B (2026-06-03) — `--flash` (one call, no research)

`flash` collapses to `START → phase_flash → p5` — ONE Opus call, **zero research, zero debate**.
Graph nodes executed: `phase_flash`, `phase_5_assemble_render` only (confirmed via progress.jsonl).

| Run | Wall-clock | graph nodes | standalone | light | Δ | #ch | evidence_refs |
|---|---|---|---|---|---|---|---|
| thorough | 1081.8s (18.0m) | p0·p2·p3·p4·p5 | 要補證據 | red | −1 | 9 | 8/9 |
| fast | 834.9s (13.9m) | p0·p2·p3·p4·p5 | 要補證據 | red | −1 | 9 | 8/9 |
| quick | 358.8s (6.0m) | p0·quick·p5 | (要補級) | yellow | 0 | 6 | 4/6 |
| **flash** | **247.4s (4.1m)** | **flash·p5** | (要補級) | yellow | 0 | 6 | **0/6 (by design)** |
| **flash ratio** | **0.23× thorough · 0.30× fast** | | | | | | |

**Time: 4.1 min (fastest), not the 1-2 min I'd estimated.** The single combined call still generates
a full challenges+signals+verdict payload in 繁中 (~240s of output tokens) — output generation is
the floor once research is removed, not round-count. evidence_refs are empty by design (no research;
the prompt enforces it and tells Albert to surface unverified points as missing_evidence).

**Quality = lowest (one-shot judgment).** 6 challenges + verdict, no research grounding, no debate.
Use for an instant sanity read only.

**Note:** the first flash benchmark run hit a transient Opus API outage ("Fatal error in message
reader" + retry stall); re-run cleanly once Opus recovered → 247.4s. Routing (flash bypasses p0)
was confirmed in both attempts.

**Four profiles shipped:** `thorough` (default, full debate, 18m) · `--fast` (research-preserving,
~0.77×, parity) · `--quick` (minimal research + one combined call, ~0.33×, ~80%) · `--flash`
(no research, one call, ~0.23×, fastest/lowest). Precedence: flash > quick > fast.
