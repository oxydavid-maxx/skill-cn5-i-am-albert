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
    """Append a markdown section to deliberation.md AND stream it to stderr live."""
    md = f"\n## {title}\n\n{body}\n"
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
        sys.stderr.write(f"\n━━━ DELIBERATION — {title} ━━━\n{body}\n")
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
    research = state.get("research") or []
    if not research:
        return "_(no research recorded)_"
    lines = ["Albert 先問自己:要 audit 這個 thesis,我得先查什麼。Queries fired + findings:"]
    for r in research[:8]:
        q = str(r.get("query", "")).strip()
        res = str(r.get("results", "")).strip().replace("\n", " ")
        lines.append(f"- **{q}** → {res[:200]}")
    return "\n".join(lines)


def render_challenges(state: dict, round_label: str = "") -> str:
    lines = []
    if round_label:
        lines.append(f"_{round_label}_")
    ambs = state.get("top_ambiguities") or []
    if ambs:
        lines.append("**3 個最危險的模糊詞 (先釘死定義):**")
        for a in ambs:
            lines.append(f"- `{a.get('term','')}` — {a.get('why_dangerous','')} → {a.get('precise_question','')}")
    chs = state.get("albert_challenges") or []
    lines.append(f"\n**Albert 生成的拷問 ({len(chs)}):**")
    for c in chs:
        lines.append(
            f"- **bone #{c.get('bone','?')}** · {c.get('challenge','')}\n"
            f"  - 為什麼 Albert 會問: {c.get('why_albert_would_ask','')}\n"
            f"  - severity={c.get('severity','?')} · current-answer={c.get('current_answer_strength','?')}"
        )
    return "\n".join(lines)


def _render_one_vote(i: int, vote: dict) -> str:
    if vote.get("_fallback"):
        return f"- **Vote {i}**: (failed / fell back — no judgment)"
    ws = vote.get("weaknesses") or []
    if not ws:
        return f"- **Vote {i}** (verdict={vote.get('verdict','?')}): no weaknesses flagged"
    parts = [f"- **Vote {i}** (verdict={vote.get('verdict','?')}):"]
    for w in ws:
        cls = w.get("classification", "?")
        issue = w.get("issue", "")
        sharp = w.get("suggested_sharpening", "")
        line = f"    - [{cls}] {issue}"
        if sharp:
            line += f" — 磨利: {sharp}"
        parts.append(line)
    return "\n".join(parts)


def render_self_critique(votes: list, assessment: dict, verdict: str) -> str:
    lines = ["三個獨立 skeptic 對同一組拷問各自攻防 (≥2 同意才算 addressable):"]
    for i, v in enumerate(votes, 1):
        lines.append(_render_one_vote(i, v))
    if assessment.get("degraded"):
        lines.append("\n**裁決: degraded — 所有 vote 都失敗,不驅動 rework。**")
    else:
        k = assessment.get("addressable_votes", 0)
        lines.append(f"\n**裁決: addressable_votes = {k} of {len(votes)} → {verdict}**")
    return "\n".join(lines)


def render_rework(round_n: int, merged: list) -> str:
    lines = [f"**Round {round_n} (rework)** — 這些 sharpenings 還沒被吃掉,所以再繞一圈重生拷問:"]
    for w in (merged or []):
        lines.append(f"- {w.get('issue','')}" + (f" → {w.get('suggested_sharpening','')}" if w.get('suggested_sharpening') else ""))
    if not merged:
        lines.append("- (no merged sharpenings recorded)")
    return "\n".join(lines)


def render_signals(merged: dict) -> str:
    pe = merged.get("premature_end_risk") or {}
    dr = merged.get("research_drift_risk") or {}
    lines = [
        f"- **premature-end risk**: {pe.get('level','?')} — {pe.get('why','')}",
        f"- **research-drift risk**: {dr.get('level','?')} — {dr.get('why','')}",
        f"- proposed action: {merged.get('proposed_next_action','?')}"
        f" → final (after signal veto): {merged.get('recommended_next_action', merged.get('proposed_next_action','?'))}",
    ]
    return "\n".join(lines)


def render_verdict(final: dict) -> str:
    light = final.get("light", "?")
    emoji = {"green": "\U0001F7E2", "yellow": "\U0001F7E1", "red": "\U0001F534"}.get(light, "")
    lines = [
        f"- verdict: {final.get('verdict_standalone','?')} {emoji} ({light})",
        f"- readiness delta: {final.get('readiness_score_delta','?')}",
        f"- recommended next action: {final.get('recommended_next_action','?')}",
        f"- one-line judgment: {final.get('reproducible_judgment','')}",
    ]
    return "\n".join(lines)
