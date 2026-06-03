"""Live, hard-required deliberation transcript for Albert runs.

Albert's reasoning chain (research -> challenges -> self-critique debate -> rework
-> verdict) is rendered from each phase's EXISTING structured output and emitted
both to runs/<run_id>/deliberation.md and to flushed stderr, so the user watches
the war-room reasoning live. Emission is fail-closed: a sink failure raises
VisibilityContractError, and a soul phase that produces output without emitting a
block fails the run via assert_emitted() (called by graph._wrap).

Mirrors albert/progress.py. No new LLM calls — phases render what they already have.
"""
import sys
from pathlib import Path
from typing import Optional

from albert.errors import VisibilityContractError
from albert import delib_layout as L

_path: Optional[Path] = None
_emitted: set = set()


def init(run_dir) -> None:
    global _path, _emitted
    _path = Path(run_dir) / "deliberation.md"
    _emitted = set()
    try:
        _path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VisibilityContractError(
            f"Failed to create deliberation directory {_path.parent}: {exc}",
            sink=str(_path.parent),
        ) from exc


def block(phase: str, title: str, body: str) -> None:
    """Emit the body markdown-free to deliberation.md AND stream it to stderr live.

    The body self-headers (render_* compose their own card/banner layout), so no
    ``##``/``━━━ title`` wrapper is added here; ``title`` is retained in the
    signature for call-site compatibility but is no longer used for formatting.
    """
    md = f"\n{body}\n"
    if _path is not None:
        try:
            with open(_path, "a", encoding="utf-8") as f:
                f.write(md)
        except OSError as exc:
            raise VisibilityContractError(
                f"Failed to append deliberation block {_path}: {exc}",
                phase=phase, sink=str(_path),
            ) from exc
    try:
        sys.stderr.write(f"\n{body}\n")
        sys.stderr.flush()
    except Exception as exc:
        raise VisibilityContractError(
            f"Failed to write deliberation block to screen: {exc}",
            phase=phase, sink="screen",
        ) from exc
    _emitted.add(phase)


def emitted(phase: str) -> bool:
    return phase in _emitted


def assert_emitted(phase: str) -> None:
    if phase not in _emitted:
        raise VisibilityContractError(
            f"Soul phase {phase} produced output but emitted no deliberation block "
            f"(deliberation is hard-required)",
            phase=phase, sink="deliberation",
        )


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
        lines = [f"拷問:{c.get('challenge', '')}",
                 f"為何問:{c.get('why_albert_would_ask', '')}"]
        refs = c.get("evidence_refs") or []
        if refs:
            lines.append(f"證據:{', '.join(str(r) for r in refs)}")
        out.append(L.card(i, len(chs), meta, lines))
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
