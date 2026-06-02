# Albert 中文化 + 卡片式 Deliberation — Design

**Date:** 2026-06-02
**Status:** approved (design dialogue 2026-06-02)

## Problem

The live deliberation stream (shipped earlier today) has two usability defects the user hit:

1. **Language:** Albert's challenges / self-critique debate / signals came out in **English**.
   Root cause: only `albert/prompts/albert_persona.txt` carries a language line ("Output
   language: match the input"), and it is prepended **only** to phase-2; phase-3
   (`self_critique_auditor`), phase-4 (`signals_action_gate`), phase-0, and verdict have
   **no** language instruction → the model defaults to English. Even phase-2's "match the
   input" is too weak when the input thesis is dense with English technical terms.

2. **排版 (layout):** the render helpers emit Markdown (`##`, `**`). In the live terminal
   stream those render as literal noise; combined with long run-on lines and 200-char raw
   research dumps, the output is a wall of text the user could not follow ("沒有編排,看不懂").

User directive 2026-06-02: "我想看中文。以及妳很多 live on screen 都沒有編排。看不懂。"

## Goal

Albert's user-visible output is in **繁體中文 (technical terms kept in English)**, and the
live deliberation renders as a clean **card layout** that reads well in BOTH the terminal
stream and the `deliberation.md` file — no Markdown control characters, numbered cards,
labeled fields, clear separators.

## Non-goals (YAGNI)

- No change to the graph, the FSM routing, the JSON schemas, or the cockpit contract
  (JSON string fields are language-agnostic; Chinese content still validates).
- No change to the `assert_emitted` hard-requirement contract or the emit/stream plumbing.
- No new feature beyond language + layout. Not touching analysis logic.

## Design

### A. Language → 繁體中文 (技術名詞保留原文)

Add an explicit, self-contained language directive to every prompt that produces
user-visible content, so no phase depends on persona being prepended:

- Files: `albert/prompts/challenge_generation.txt`, `self_critique_auditor.txt`,
  `signals_action_gate.txt`, `verdict_render.txt`, `ambiguity_hunt.txt`,
  `intake_grounding.txt`, `search_reflection.txt`.
- Directive (appended near the top of each): a line equivalent to
  「**以繁體中文輸出。技術名詞(TC4, ASIL, Ethernet, AUTOSAR, gateway, MCU, zonal, OEM…)
  保留英文原文,不要硬翻。**」
- `albert/prompts/albert_persona.txt`: replace the weak "Output language: match the input."
  with the explicit 繁體中文 directive above.
- `search_reflection` / `intake_grounding` drive web-search query generation — the raw
  search query strings may stay in English (do not force-translate them); the 繁中 directive
  applies to user-facing reasoning text, not to the query strings sent to the search tool.

Schema impact: none. `verdict_standalone` enum is already Chinese
(可推進/要補證據/方向錯/產品定義不完整).

### B. 卡片式排版 — `albert/delib_layout.py` (new, pure)

A small pure-formatting module so `deliberation.py` render_* stay thin and the layout is
unit-testable in isolation. No Markdown symbols (`#`, `*`); only box-drawing + plain text.

Primitives:
- `header(title: str) -> str` — a `═`-bordered banner:
  ```
  ════════════════════════════════════
    PHASE 2 ─ 生成拷問
  ════════════════════════════════════
  ```
- `section(label: str) -> str` — `▍<label>` section marker.
- `card(index: int, total: int, meta: str, lines: list[str]) -> str` — a numbered card:
  ```
  ┌─ [1/10]  骨#2 · 嚴重度:高 · 現答:弱
  │  拷問:…
  │  為何問:…
  └────────────────────────────────
  ```
- `kv(label: str, value: str) -> str` — a `標籤:值` line (for inside cards).
- `bullet(text: str, indent: int = 0) -> str` — a `·`/`▸` bullet line.
- `truncate(text: str, n: int = 100) -> str` — collapse whitespace/newlines, cut to n chars
  with `…`. Used to keep research findings to one line.
- Constants for box width so dividers align.

All primitives return plain strings; deterministic; no I/O.

### B2. Rewrite `deliberation.py` render_* to compose the primitives

- `render_research(state)` — header「PHASE 0 ─ 研究打底」+ one line per query:
  `· <query> → <truncate(takeaway, ~90)>`. Drop the 200-char raw dump.
- `render_challenges(state, round_label="")` — header「PHASE 2 ─ 生成拷問」(+「Round N(rework)」
  if round_label); section「▍先釘死 3 個最危險的模糊詞」with the 3 ambiguities as short cards;
  section「▍拷問(共 N 條)」with each challenge as a `card`:
  meta = `骨#{bone} · 嚴重度:{嚴重度中文} · 現答:{現答中文}`, lines = `拷問:{challenge}` /
  `為何問:{why_albert_would_ask}`.
- `render_self_critique(votes, assessment, verdict)` — header「PHASE 3 ─ 自我辯論」+ a one-line
  rule note「3 票獨立攻防,≥2 同意才算『可解決』」; one card per vote:
  meta = `第 {i} 票 · 裁決:{verdict}`, lines = per weakness
  `▸[{可解決|殘留}] {issue}` (+ `   磨利:{suggested_sharpening}` if present); fallback vote →
  `(失敗,無判斷)`. Footer line: degraded →「裁決:degraded — 所有票失敗,不驅動 rework」else
  「裁決:可解決票 = {k} / {n} → {verdict}」.
- `render_rework(round_n, merged)` — header「── 重做決策 ──」+「Round {n}:這些磨利還沒被吃掉,
  再繞一圈重生拷問」+ each merged item as a bullet `· {issue} → {sharpening}`.
- `render_signals(merged)` — header「PHASE 4 ─ Signals & 行動閘」+ kv lines:
  `提前結束風險:{level中文} — {why}` / `研究偏移風險:{level中文} — {why}` /
  `建議行動:{proposed} → 經訊號否決後:{final}`.
- `render_verdict(final)` — header「PHASE 5 ─ 裁決」+ kv lines: `判定:{verdict_standalone} {emoji}` /
  `準備度變化:{delta}` / `建議下一步:{recommended_next_action}` / `一句話判斷:{reproducible_judgment}`.

Label mappings (constants in `delib_layout.py` or `deliberation.py`):
- severity / level: `high→高, medium→中, low→低, none→無, unknown→未知`.
- current_answer_strength: `weak→弱, medium→中, strong→強`.
- classification: `addressable→可解決, residual→殘留`.
- light emoji unchanged (🟢🟡🔴).

The phase-name first arg to `deliberation.block(...)` is UNCHANGED (still the exact graph
node name) so `assert_emitted` keeps working. Only the rendered `body` text changes.

## Testing

- `tests/test_delib_layout.py`: each primitive returns the expected structure; `header`
  contains `═` and the title; `card` contains `┌─ [`, the meta, the lines, and a `└─`
  divider; outputs contain NO `#` or `*` (markdown-free); `truncate` collapses newlines and
  caps length with `…`.
- Update `tests/test_deliberation.py` render tests: assert the new **Chinese** labels and
  card structure instead of the old English substrings — e.g. `render_challenges` output
  contains `拷問` and `骨#3` and `嚴重度:高`; `render_self_critique` contains `第 1 票`,
  `可解決`, and `可解決票 = 2 / 3 → REWORK`; `render_verdict` contains `判定` and the light
  emoji; no output contains `##` or `**`.
- `tests/test_deliberation_phases.py`: update the substring assertions to the new Chinese
  card markers (e.g. phase_2 emits `骨#1`; phase_3 emits `第 1 票`). The emit/contract
  behavior assertions stay the same.
- Full suite stays green.

## Files

- Modify: `albert/prompts/{challenge_generation,self_critique_auditor,signals_action_gate,
  verdict_render,ambiguity_hunt,intake_grounding,search_reflection,albert_persona}.txt`
- Create: `albert/delib_layout.py`, `tests/test_delib_layout.py`
- Modify: `albert/deliberation.py` (rewrite render_*), `tests/test_deliberation.py`,
  `tests/test_deliberation_phases.py`
- Unchanged: `albert/graph.py`, schemas, cockpit contract, emit/assert_emitted plumbing.
