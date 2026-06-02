# Albert Speedup v3.2 — Cut the Marginal (雞肋) Processes

- **Skill:** `skill-cn5-i-am-albert`
- **Date:** 2026-06-02
- **Status:** design approved (free, low-quality-impact cuts; ~11.4 → ~8.7 min)
- **Constraint:** NO paid services (no Tavily/Brave key, no API-key account / fast mode). Stay on
  the free OAuth subscription. Sonnet 4.6 benchmark showed no speed win (TTFT/search-bound), so
  these cuts are model-agnostic.
- **Builds on:** v3 (merge P4+5, single-wave P0, trim, parallel votes) — measured **682s ≈ 11.4 min**.

## 1. The two marginal processes (measured + code-confirmed)

**雞肋 #1 — self-critique re-searches what's already grounded.** Phase 3's 3 parallel votes each
run with `allow_tools=True` and a prompt telling them to "Use WebSearch to check whether a challenge
is research-backed." But the challenges were already grounded by Phase-0 research + Phase-2
generation. Re-searching in the critique is redundant work, AND 3 concurrent WebSearches contend on
the rate limit — that's why Phase 3 is ~126s.

**雞肋 #2 — ambiguity-hunt is a separate round-trip that overlaps the challenges.** Phase 1 (84s)
produces the "3 most dangerous ambiguities," but the dogfood shows they re-appear as challenges
(challenge #1 "客戶要 = which OEM" IS ambiguity #1). A whole Opus round-trip for content the next
phase re-derives.

## 2. Changes

### 2.1 Self-critique: judge from existing grounding, don't re-search (−~80s)
In `albert/phases/phase_3_self_critique_audit.py`:
- `_one_vote` calls `call_claude(..., allow_tools=False)` (was `True`); drop `max_turns` to the
  default (no tool turns needed).
- Inject a digest of `state["research"]` (the Phase-0 findings) into the vote `payload`/context so
  the critique judges "research-backed?" from the **already-gathered** evidence, not a fresh search.
- Update `self_critique_auditor.txt`: replace "Use WebSearch to check…" with "Judge whether each
  challenge is supported by the provided research findings; do not search."
- Everything else unchanged: N=3 parallel, `_aggregate_votes`, `_converged`, degraded guard,
  merged-addressable write. **Each vote ~126s → ~40-50s** (no in-vote search round-trips, no
  3-way search contention). Quality impact low: the auditor still classifies sharp/ADDRESSABLE/
  RESIDUAL — it just uses the research already in hand.

### 2.2 Merge ambiguity-hunt into challenge generation (−84s)
- `albert/schemas.py`: `CHALLENGE_GENERATION` gains `top_ambiguities` (exactly-3 array, same item
  shape as `AMBIGUITY_HUNT`).
- `albert/phases/phase_2_challenge_generation.py`: the call now also returns `top_ambiguities`;
  `phase_2` writes `state["top_ambiguities"]` (defensive: pad/truncate to 3, stub on miss — reuse
  Phase-1's `_stub` logic).
- `albert/prompts/challenge_generation.txt`: prepend the ambiguity-hunt instruction ("first surface
  the 3 most dangerous ambiguities, then the challenges").
- Graph (`albert/graph.py`): remove the `phase_1_ambiguity_hunt` node; wire `phase_0 → phase_2`.
  Keep `phase_1_ambiguity_hunt.py` + its module (in case the standalone phase is wanted later) but
  it's no longer in the graph. The Phase-2 context still references the ambiguities it now produces
  in the same call.
- Self-critique + Phase-4 read `state["top_ambiguities"]` exactly as before (unchanged consumers).
- **Saves the 84s round-trip.** Quality impact low: same 3 ambiguities, produced in the same call
  that uses them → more coherent, not less.

### 2.3 websearch default max_turns 3 → 2 (−~30s, minor)
`albert/sdk_client.py` `_websearch_max_turns()` default `"3"` → `"2"`. Still allows one search +
one refine. Env-tunable to restore depth. Mild quality risk.

## 3. Expected effect

| Change | Δ | Quality |
|---|---|---|
| 2.1 self-critique no re-search | −~80s | low (judges from existing research) |
| 2.2 merge ambiguity → challenge | −84s | low (overlap; more coherent) |
| 2.3 max_turns 3→2 | −~30s | mild (env-tunable) |

**Projected: 682s → ~490-520s ≈ ~8.5 min**, quality maintained. Combined with the established
floor analysis, this is the last free, low-risk squeeze; below ~8 min needs paid infra (declined)
or soul-touching cuts.

## 4. Testing
- `tests/test_phase_3_audit.py` — votes now `allow_tools=False`; research digest in context; the
  3 existing cases (majority→REWORK, minority→EXHAUSTED, all-fail→degraded+EXHAUSTED) still pass.
- `tests/test_phase_2_challenge.py` — challenge call returns `top_ambiguities`; `state["top_ambiguities"]`
  populated (exactly 3); stub-on-miss; existing merge/AND-fold/rework-feedback cases still pass.
- `tests/test_graph_topology.py` — `phase_1_ambiguity_hunt` no longer a node; `phase_0 → phase_2`
  edge present; no orphan; exhaustion loop (phase_3→phase_2) intact.
- `tests/test_self_critique_loop.py` (e2e) — still green with the new topology.
- `tests/test_websearch_max_turns.py` — default now 2.

## 5. Risks / open
- **Merging ambiguity** — the one call now does more; ensure the StructuredOutput schema and prompt
  keep the 3 ambiguities distinct from the challenges (don't let them collapse). The defensive
  pad-to-3 guards an under-produced list.
- **Self-critique without search** — if Phase-0 research is empty (standalone with no grounding),
  the critique judges from the challenges alone; acceptable (it still checks sharpness/thesis).
- **Re-dogfood required** — confirm ~8.5 min AND quality parity (competitors named, first-principles
  catch, moat test, 🔴/Δ−2) before declaring done.
