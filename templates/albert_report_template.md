# Albert Review — {proposal_title}

**Audit verdict:** {verdict} · would_survive_leadership={would_survive_leadership} · degraded={degraded}

**Recommended next action:** `{recommended_next_action}` — {rationale}

**premature_end:** {premature_end_risk.level} (grounded_in={premature_end_risk.grounded_in}) · **drift:** {research_drift_risk.level}

**Standalone:** {verdict_standalone} {light_emoji} · delta {readiness_score_delta}

## 最危險的 3 個模糊點

- **{ambiguity.term}** — {ambiguity.why_dangerous} → {ambiguity.precise_question}

## 靈魂拷問 (albert_challenges)

1. [{challenge.status}/sev={challenge.severity}/{challenge.generator}] {challenge.challenge}  ↳ {challenge.next_action}

## Weak points

- {weak_point}

## Recommended next probe

{probe.priority}. [{probe.kind}] {probe.probe} — {probe.why}

## 可複用判斷

{reproducible_judgment}

---

> Reference layout for `albert/render.py::render_report`. The renderer emits exactly these
> sections in this order: title, audit-verdict line, recommended-next-action + rationale,
> rule-grounded risk lines (premature_end / drift), standalone verdict + light + readiness
> delta, the three most dangerous ambiguities, the albert_challenges (靈魂拷問), weak points,
> the priority-ranked recommended next probe, and the reproducible-judgment block. The
> machine-readable counterpart is `albert_challenge.json` (schema `schemas/albert_challenge.schema.json`).
