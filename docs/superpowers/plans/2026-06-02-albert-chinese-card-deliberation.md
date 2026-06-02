# Albert 中文化 + 卡片式 Deliberation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Albert's user-visible output is 繁體中文 (technical terms kept English), and the live deliberation renders as a clean, markdown-free card layout that reads in both the terminal stream and `deliberation.md`.

**Architecture:** New pure module `albert/delib_layout.py` holds box-drawing/card primitives + zh label maps. `albert/deliberation.py` render_* are rewritten to compose those primitives (each starts with a `header()` banner), and `block()` is simplified to emit the body markdown-free (no `##`/`━━━ title` wrapper — the body self-headers). Every user-visible prompt gets an explicit 繁體中文 directive.

**Tech Stack:** Python 3, pytest. No graph/schema/contract changes.

---

## Reference

- `albert/deliberation.py` current `block(phase, title, body)` writes `\n## {title}\n\n{body}\n` to the file and `\n━━━ DELIBERATION — {title} ━━━\n{body}\n` to stderr, then `_emitted.add(phase)`. `init`/`emitted`/`assert_emitted` are the contract — DO NOT change those.
- render_* current signatures (keep them): `render_research(state)`, `render_challenges(state, round_label="")`, `render_self_critique(votes, assessment, verdict)`, `render_rework(round_n, merged)`, `render_signals(merged)`, `render_verdict(final)`.
- Phases call `deliberation.block("<node_name>", "<title>", render_x(...))`. The `<node_name>` (1st arg) MUST stay the exact graph node name (assert_emitted depends on it). The title (2nd arg) is now cosmetic.

---

## Task 1: `albert/delib_layout.py` — pure card primitives + zh maps

**Files:**
- Create: `albert/delib_layout.py`
- Test: `tests/test_delib_layout.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_delib_layout.py
from albert import delib_layout as L


def test_header_has_bar_and_title_no_markdown():
    h = L.header("PHASE 2 ─ 生成拷問")
    assert "═" in h
    assert "PHASE 2 ─ 生成拷問" in h
    assert "#" not in h and "*" not in h


def test_section_marker():
    assert L.section("拷問(共 10 條)") == "▍拷問(共 10 條)"


def test_card_structure():
    c = L.card(1, 10, "骨#2 · 嚴重度:高 · 現答:弱", ["拷問:X 在成長嗎?", "為何問:慢性失血"])
    assert "┌─ [1/10]" in c
    assert "骨#2 · 嚴重度:高 · 現答:弱" in c
    assert "│  拷問:X 在成長嗎?" in c
    assert "│  為何問:慢性失血" in c
    assert "└─" in c
    assert "#" not in c.replace("骨#2", "") and "*" not in c  # no markdown control chars


def test_kv_and_bullet():
    assert L.kv("提前結束風險", "高 — 6 條未解") == "提前結束風險:高 — 6 條未解"
    assert L.bullet("重點") == "· 重點"
    assert L.bullet("縮排", indent=3) == "   · 縮排"


def test_truncate_collapses_and_caps():
    assert L.truncate("a\n  b   c", 100) == "a b c"
    out = L.truncate("x" * 200, 90)
    assert len(out) <= 91 and out.endswith("…")


def test_zh_label_maps():
    assert L.sev_zh("high") == "高" and L.sev_zh("low") == "低" and L.sev_zh("medium") == "中"
    assert L.strength_zh("weak") == "弱" and L.strength_zh("strong") == "強"
    assert L.cls_zh("addressable") == "可解決" and L.cls_zh("residual") == "殘留"
    assert L.sev_zh("unknown") == "未知"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_delib_layout.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'albert.delib_layout'`.

- [ ] **Step 3: Write minimal implementation**

```python
# albert/delib_layout.py
"""Pure plain-text card-layout primitives for the deliberation transcript.

No Markdown control characters (#, *) — only box-drawing + plain text — so the
output reads cleanly in BOTH the live terminal stream and deliberation.md.
Deterministic; no I/O.
"""

BOX_W = 60

_SEV = {"high": "高", "medium": "中", "low": "低", "none": "無", "unknown": "未知"}
_STR = {"weak": "弱", "medium": "中", "strong": "強"}
_CLS = {"addressable": "可解決", "residual": "殘留"}


def sev_zh(x) -> str:
    return _SEV.get(str(x), str(x))


def strength_zh(x) -> str:
    return _STR.get(str(x), str(x))


def cls_zh(x) -> str:
    return _CLS.get(str(x), str(x))


def header(title: str) -> str:
    bar = "═" * BOX_W
    return f"{bar}\n  {title}\n{bar}"


def section(label: str) -> str:
    return f"▍{label}"


def kv(label: str, value: str) -> str:
    return f"{label}:{value}"


def bullet(text: str, indent: int = 0) -> str:
    return (" " * indent) + f"· {text}"


def truncate(text, n: int = 100) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= n else t[:n].rstrip() + "…"


def card(index: int, total: int, meta: str, lines: list) -> str:
    top = f"┌─ [{index}/{total}]  {meta}"
    body = "\n".join(f"│  {ln}" for ln in lines)
    bot = "└" + "─" * (BOX_W - 1)
    return f"{top}\n{body}\n{bot}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_delib_layout.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git -c commit.gpgsign=false add albert/delib_layout.py tests/test_delib_layout.py
git -c commit.gpgsign=false commit -m "feat(delib): pure card-layout primitives + zh label maps"
```

---

## Task 2: Rewrite `deliberation.py` render_* (zh + cards) and simplify `block()`

**Files:**
- Modify: `albert/deliberation.py`
- Test: `tests/test_deliberation.py` (update render + block tests), `tests/test_deliberation_phases.py` (update substrings)

- [ ] **Step 1: Update the failing tests** — replace the existing render tests AND the `test_block_writes_file_and_stderr` test in `tests/test_deliberation.py` with these (keep the contract tests `test_emitted_tracks_phases`, `test_assert_emitted_*`, `test_init_resets_emitted_set`, `test_block_raises_when_dir_unwritable` unchanged):

```python
# replace test_block_writes_file_and_stderr with this (block now emits body markdown-free):
def test_block_writes_file_and_stderr(tmp_path, capsys):
    deliberation.init(tmp_path)
    deliberation.block("phase_2_challenge_generation", "ignored-title", "卡片內容XYZ")
    md = (tmp_path / "deliberation.md").read_text(encoding="utf-8")
    assert "卡片內容XYZ" in md
    assert "##" not in md  # no markdown heading
    err = capsys.readouterr().err
    assert "卡片內容XYZ" in err

# replace ALL render_* tests with these:
from albert import deliberation as D


def test_render_research_zh():
    state = {"research": [{"query": "TC4 roadmap", "results": "AURIX TC4 targets high-end ZCU ...\n more"}]}
    out = D.render_research(state)
    assert "PHASE 0" in out and "TC4 roadmap" in out
    assert "##" not in out and "**" not in out


def test_render_challenges_zh_cards():
    state = {"top_ambiguities": [{"term": "mid-tier", "why_dangerous": "未定義", "precise_question": "哪個 OEM?"}],
             "albert_challenges": [{"bone": 3, "challenge": "客戶是誰?", "why_albert_would_ask": "無 named socket",
                                    "severity": "high", "current_answer_strength": "weak"}]}
    out = D.render_challenges(state)
    assert "PHASE 2" in out
    assert "拷問" in out
    assert "骨#3" in out
    assert "嚴重度:高" in out and "現答:弱" in out
    assert "客戶是誰?" in out
    assert "┌─ [1/1]" in out
    assert "##" not in out and "**" not in out


def test_render_self_critique_zh():
    votes = [
        {"weaknesses": [{"classification": "addressable", "issue": "無量", "suggested_sharpening": "給 SOP"}], "verdict": "rework"},
        {"weaknesses": [{"classification": "residual", "issue": "總經風險"}], "verdict": "exhausted"},
        {"weaknesses": [{"classification": "addressable", "issue": "無量", "suggested_sharpening": "給 SOP"}], "verdict": "rework"},
    ]
    assessment = {"addressable_votes": 2, "degraded": False, "merged": []}
    out = D.render_self_critique(votes, assessment, "REWORK")
    assert "PHASE 3" in out
    assert "第 1 票" in out and "第 2 票" in out and "第 3 票" in out
    assert "可解決" in out and "殘留" in out
    assert "無量" in out and "磨利:給 SOP" in out
    assert "可解決票 = 2 / 3 → REWORK" in out
    assert "##" not in out and "**" not in out


def test_render_self_critique_degraded_zh():
    votes = [{"weaknesses": [], "verdict": "exhausted", "_fallback": True}]
    assessment = {"addressable_votes": 0, "degraded": True, "merged": []}
    out = D.render_self_critique(votes, assessment, "EXHAUSTED")
    assert "degraded" in out.lower()


def test_render_rework_zh():
    merged = [{"issue": "無量", "suggested_sharpening": "給 SOP window"}]
    out = D.render_rework(2, merged)
    assert "Round 2" in out
    assert "給 SOP window" in out


def test_render_signals_zh():
    merged = {"premature_end_risk": {"level": "high", "why": "6 條未解"},
              "research_drift_risk": {"level": "low", "why": "在原集合"},
              "proposed_next_action": "pull_human", "recommended_next_action": "pull_human"}
    out = D.render_signals(merged)
    assert "PHASE 4" in out
    assert "提前結束風險:高 — 6 條未解" in out
    assert "研究偏移風險:低 — 在原集合" in out
    assert "pull_human" in out
    assert "##" not in out and "**" not in out


def test_render_verdict_zh():
    final = {"verdict_standalone": "要補證據", "light": "red", "readiness_score_delta": 1,
             "recommended_next_action": "pull_human", "reproducible_judgment": "方向對但證據不足"}
    out = D.render_verdict(final)
    assert "PHASE 5" in out
    assert "判定:要補證據" in out
    assert "🔴" in out
    assert "準備度變化:1" in out
    assert "方向對但證據不足" in out
    assert "##" not in out and "**" not in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `py -3 -m pytest tests/test_deliberation.py -v`
Expected: FAIL (old render output is English/markdown; `block` still writes `##`).

- [ ] **Step 3: Rewrite `albert/deliberation.py`** — add `from albert import delib_layout as L` at the top; change `block()`'s two writes to be markdown-free; replace ALL render_* functions. The `block()` change:

In `block()`, change the file write from:
```python
    md = f"\n## {title}\n\n{body}\n"
```
to:
```python
    md = f"\n{body}\n"
```
and change the stderr write from:
```python
        sys.stderr.write(f"\n━━━ DELIBERATION — {title} ━━━\n{body}\n")
```
to:
```python
        sys.stderr.write(f"\n{body}\n")
```
(Keep everything else in `block` — the `_path` guard, the `OSError`/`Exception` → `VisibilityContractError`, and `_emitted.add(phase)` — unchanged. `title` stays in the signature, now unused for formatting.)

Replace the render_* functions with:
```python
def render_research(state: dict) -> str:
    out = [L.header("PHASE 0 ─ 研究打底")]
    research = state.get("research") or []
    if not research:
        out.append("(無研究記錄)")
        return "\n".join(out)
    out.append("Albert 先問:要 audit 這個 thesis,得先查什麼。")
    for r in research[:8]:
        q = str(r.get("query", "")).strip()
        out.append(L.bullet(f"{q} → {L.truncate(r.get('results', ''), 90)}"))
    return "\n".join(out)


def render_challenges(state: dict, round_label: str = "") -> str:
    title = "PHASE 2 ─ 生成拷問" + (f"({round_label})" if round_label else "")
    out = [L.header(title)]
    ambs = state.get("top_ambiguities") or []
    if ambs:
        out.append(L.section("先釘死最危險的模糊詞"))
        for i, a in enumerate(ambs, 1):
            out.append(L.card(i, len(ambs), f"模糊詞:{a.get('term', '')}",
                              [f"危險:{a.get('why_dangerous', '')}",
                               f"釘死:{a.get('precise_question', '')}"]))
    chs = state.get("albert_challenges") or []
    out.append(L.section(f"拷問(共 {len(chs)} 條)"))
    for i, c in enumerate(chs, 1):
        meta = (f"骨#{c.get('bone', '?')} · 嚴重度:{L.sev_zh(c.get('severity'))}"
                f" · 現答:{L.strength_zh(c.get('current_answer_strength'))}")
        out.append(L.card(i, len(chs), meta,
                          [f"拷問:{c.get('challenge', '')}",
                           f"為何問:{c.get('why_albert_would_ask', '')}"]))
    return "\n".join(out)


def _vote_lines(v: dict) -> list:
    if v.get("_fallback"):
        return ["(失敗,無判斷)"]
    lines = []
    for w in (v.get("weaknesses") or []):
        lines.append(f"▸[{L.cls_zh(w.get('classification'))}] {w.get('issue', '')}")
        if w.get("suggested_sharpening"):
            lines.append(f"   磨利:{w.get('suggested_sharpening')}")
    return lines or ["(無弱點)"]


def render_self_critique(votes: list, assessment: dict, verdict: str) -> str:
    out = [L.header("PHASE 3 ─ 自我辯論"),
           "3 票獨立攻防,≥2 同意才算「可解決」"]
    for i, v in enumerate(votes, 1):
        out.append(L.card(i, len(votes), f"第 {i} 票 · 裁決:{v.get('verdict', '?')}", _vote_lines(v)))
    if assessment.get("degraded"):
        out.append("裁決:degraded — 所有票失敗,不驅動 rework")
    else:
        out.append(f"裁決:可解決票 = {assessment.get('addressable_votes', 0)} / {len(votes)} → {verdict}")
    return "\n".join(out)


def render_rework(round_n: int, merged: list) -> str:
    out = [L.header("── 重做決策 ──"),
           f"Round {round_n}:這些磨利還沒被吃掉,再繞一圈重生拷問:"]
    if not merged:
        out.append(L.bullet("(無 merged 磨利記錄)"))
    for w in (merged or []):
        s = w.get("issue", "")
        if w.get("suggested_sharpening"):
            s += f" → {w.get('suggested_sharpening')}"
        out.append(L.bullet(s))
    return "\n".join(out)


def render_signals(merged: dict) -> str:
    pe = merged.get("premature_end_risk") or {}
    dr = merged.get("research_drift_risk") or {}
    final = merged.get("recommended_next_action", merged.get("proposed_next_action", "?"))
    return "\n".join([
        L.header("PHASE 4 ─ Signals & 行動閘"),
        L.kv("提前結束風險", f"{L.sev_zh(pe.get('level'))} — {pe.get('why', '')}"),
        L.kv("研究偏移風險", f"{L.sev_zh(dr.get('level'))} — {dr.get('why', '')}"),
        L.kv("建議行動", f"{merged.get('proposed_next_action', '?')} → 經訊號否決後:{final}"),
    ])


def render_verdict(final: dict) -> str:
    emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(final.get("light", ""), "")
    return "\n".join([
        L.header("PHASE 5 ─ 裁決"),
        L.kv("判定", f"{final.get('verdict_standalone', '?')} {emoji}"),
        L.kv("準備度變化", str(final.get("readiness_score_delta", "?"))),
        L.kv("建議下一步", str(final.get("recommended_next_action", "?"))),
        L.kv("一句話判斷", str(final.get("reproducible_judgment", ""))),
    ])
```

- [ ] **Step 4: Update `tests/test_deliberation_phases.py`** substrings to the new Chinese markers:

Change `assert "bone #1" in ...` → `assert "骨#1" in ...` in `test_phase_2_emits_block`; change `assert "Vote 1" in md and "no volume" in md` → `assert "第 1 票" in md and "no volume" in md` in `test_phase_3_emits_debate`. (The monkeypatched data uses English issue text "no volume" — keep that; only the structural labels change.)

- [ ] **Step 5: Run the full suite**

Run: `py -3 -m pytest -q`
Expected: PASS — all tests green (the deliberation render/block/phase tests now assert the zh card layout).

- [ ] **Step 6: Eyeball the layout** — render a sample to confirm it looks like the approved card preview:

```bash
py -3 -c "from albert import deliberation as D; print(D.render_challenges({'top_ambiguities':[{'term':'中間層 socket','why_dangerous':'三種混用','precise_question':'哪個 OEM?'}],'albert_challenges':[{'bone':2,'challenge':'socket 在成長還是被 zonal 吃掉?','why_albert_would_ask':'慢性失血','severity':'high','current_answer_strength':'weak'}]}))"
```
Expected: a `═` banner, a `▍` section, and a `┌─ [1/1] 骨#2 · 嚴重度:高 · 現答:弱` card with `└─` divider; no `#`/`*` noise.

- [ ] **Step 7: Commit**

```bash
git -c commit.gpgsign=false add albert/deliberation.py tests/test_deliberation.py tests/test_deliberation_phases.py
git -c commit.gpgsign=false commit -m "feat(delib): zh card-layout render_* + markdown-free block()"
```

---

## Task 3: 繁體中文 directive in every user-visible prompt

**Files:**
- Modify: `albert/prompts/albert_persona.txt`, `challenge_generation.txt`, `self_critique_auditor.txt`, `signals_action_gate.txt`, `verdict_render.txt`, `ambiguity_hunt.txt`, `intake_grounding.txt`, `search_reflection.txt`
- Test: `tests/test_prompts_language.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompts_language.py
from albert.utils import load_prompt

_USER_VISIBLE = ["albert_persona", "challenge_generation", "self_critique_auditor",
                 "signals_action_gate", "verdict_render", "ambiguity_hunt",
                 "intake_grounding", "search_reflection"]


def test_every_user_visible_prompt_has_zh_directive():
    for name in _USER_VISIBLE:
        text = load_prompt(name)
        assert "繁體中文" in text, f"{name} missing 繁體中文 directive"


def test_persona_no_longer_says_match_the_input():
    assert "match the input" not in load_prompt("albert_persona").lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3 -m pytest tests/test_prompts_language.py -v`
Expected: FAIL (prompts lack the directive; persona still says "match the input").

- [ ] **Step 3: Edit the prompts.** In `albert/prompts/albert_persona.txt`, replace the line `(the moat test). Output language: match the input.` so it ends with the explicit directive instead — change `Output language: match the input.` to:
```
Output language: 以繁體中文輸出。技術名詞(TC4, ASIL, Ethernet, AUTOSAR, gateway, MCU, zonal, OEM…)保留英文原文,不要硬翻。
```

In each of `challenge_generation.txt`, `self_critique_auditor.txt`, `signals_action_gate.txt`, `verdict_render.txt`, `ambiguity_hunt.txt`, `intake_grounding.txt`, `search_reflection.txt`, append a new final line:
```
以繁體中文輸出。技術名詞(TC4, ASIL, Ethernet, AUTOSAR, gateway, MCU, zonal, OEM…)保留英文原文,不要硬翻。
```
For `search_reflection.txt` and `intake_grounding.txt` ALSO add, right after that line:
```
(網路搜尋的 query 字串可保留英文,不需翻譯;上面的中文規則只適用於你給人看的推理文字。)
```

- [ ] **Step 4: Run to verify it passes**

Run: `py -3 -m pytest tests/test_prompts_language.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite**

Run: `py -3 -m pytest -q`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git -c commit.gpgsign=false add albert/prompts/ tests/test_prompts_language.py
git -c commit.gpgsign=false commit -m "feat(prompts): enforce 繁體中文 output (keep technical terms English) in all user-visible prompts"
```

---

## Self-Review

**1. Spec coverage:**
- Language directive in all 8 prompts + persona "match the input" removed → Task 3 + its tests. ✓
- search-query English carve-out → Task 3 Step 3. ✓
- `delib_layout.py` primitives (header/section/card/kv/bullet/truncate) + zh maps → Task 1. ✓
- render_* rewritten to cards + zh, markdown-free → Task 2 Step 3. ✓
- block() markdown-free (no double banner) → Task 2 Step 3. ✓
- zh label maps (sev/strength/cls) → Task 1 + used in render. ✓
- phase-name 1st arg unchanged (assert_emitted intact) → Task 2 keeps block signature + node-name arg. ✓
- tests: layout primitives, render zh/cards, phase substrings, prompt directive → Tasks 1-3. ✓

**2. Placeholder scan:** No TBD/TODO. All code blocks complete.

**3. Type consistency:** `header/section/kv/bullet/truncate/card` + `sev_zh/strength_zh/cls_zh` names identical across Task 1 def and Task 2 usage (`L.<name>`). render_* signatures unchanged from the existing callers. `card(index, total, meta, lines)` call sites match the def. ✓
