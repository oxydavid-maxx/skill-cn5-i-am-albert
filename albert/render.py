"""Assemble the albert_challenge contract (AuditResult-aligned), degraded guard, markdown report."""
import json
from pathlib import Path
from albert.errors import DegradedEmissionError

_LIGHT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def enforce_degraded_guard(degraded: bool, light: str) -> None:
    if degraded and light == "green":
        raise DegradedEmissionError("green light on a degraded run is forbidden", "degraded_green")


def build_challenge(state: dict) -> dict:
    return {
        "verdict": state.get("verdict", "rework"),
        "audited_answer": state.get("current_answer", ""),
        "would_survive_leadership": bool(state.get("would_survive_leadership", False)),
        "top_ambiguities": state.get("top_ambiguities", []),
        "albert_challenges": state.get("albert_challenges", []),
        "weak_points": state.get("weak_points", []),
        "missing_business_context": state.get("missing_business_context", []),
        "missing_evidence": state.get("missing_evidence", []),
        "questions_albert_would_ask": state.get("questions_albert_would_ask", []),
        "premature_end_risk": state.get("premature_end_risk", {"level": "low", "grounded_in": "inferred"}),
        "research_drift_risk": state.get("research_drift_risk", {"level": "low", "grounded_in": "inferred"}),
        "recommended_next_probe": state.get("recommended_next_probe", []),
        "recommended_next_action": state.get("recommended_next_action", "continue_research"),
        "rationale": state.get("rationale", ""),
        "decision_gate": state.get("decision_gate", {"can_decide_now": [], "cannot_decide": [], "owners": []}),
        "readiness_score_delta": int(state.get("readiness_score_delta", 0)),
        "reproducible_judgment": state.get("reproducible_judgment", ""),
        "degraded": bool(state.get("degraded", False)),
        "run_status": state.get("run_status", "failed"),
        "verdict_standalone": state.get("verdict_standalone", "產品定義不完整"),
        "light": state.get("light", "red"),
    }


def write_challenge_json(state: dict, run_dir: Path) -> str:
    p = Path(run_dir) / "albert_challenge.json"
    p.write_text(json.dumps(build_challenge(state), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def render_report(state: dict) -> str:
    c = build_challenge(state)
    L = [f"# Albert Review — {state.get('proposal', {}).get('title', '(current answer)')}", "",
         f"**Audit verdict:** {c['verdict']} · would_survive_leadership={c['would_survive_leadership']} · "
         f"degraded={c['degraded']}", "",
         f"**Recommended next action:** `{c['recommended_next_action']}` — {c['rationale']}", "",
         f"**premature_end:** {c['premature_end_risk'].get('level')} "
         f"(grounded_in={c['premature_end_risk'].get('grounded_in')}) · "
         f"**drift:** {c['research_drift_risk'].get('level')}", "",
         f"**Standalone:** {c['verdict_standalone']} {_LIGHT.get(c['light'],'')} · delta {c['readiness_score_delta']}",
         "", "## 最危險的 3 個模糊點"]
    L += [f"- **{a.get('term','')}** — {a.get('why_dangerous','')} → {a.get('precise_question','')}"
          for a in c["top_ambiguities"]]
    L += ["", "## 靈魂拷問 (albert_challenges)"]
    for i, q in enumerate(c["albert_challenges"], 1):
        L.append(f"{i}. [{q.get('status','')}/sev={q.get('severity','')}/{q.get('generator','')}] "
                 f"{q.get('challenge','')}  ↳ {q.get('next_action','')}")
    L += ["", "## Weak points"] + [f"- {w}" for w in c["weak_points"]]
    L += ["", "## Recommended next probe"]
    L += [f"{p.get('priority','')}. [{p.get('kind','')}] {p.get('probe','')} — {p.get('why','')}"
          for p in c["recommended_next_probe"]]
    L += ["", "## 可複用判斷", c["reproducible_judgment"] or "(none)"]
    return "\n".join(L)


def write_report(state: dict, run_dir: Path) -> str:
    p = Path(run_dir) / "albert_review.md"
    p.write_text(render_report(state), encoding="utf-8")
    return str(p)
