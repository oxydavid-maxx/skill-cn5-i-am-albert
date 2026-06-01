"""Deterministic visibility receipts for Albert runs."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from albert.errors import VisibilityContractError


PHASE_TITLES = {
    "phase_0_research": "Phase 0 Research",
    "phase_1_is_isnt": "Phase 1 IS / IS NOT",
    "phase_2_why_analysis": "Phase 2 Why Analysis",
    "phase_3_rc_audit": "Phase 3 Root-Cause Audit",
    "phase_4_actions": "Phase 4 Corrective / Prevention Actions",
    "phase_5_prevention_audit": "Phase 5 Prevention Audit",
    "phase_6_verification": "Phase 6 Verification",
    "phase_7_report": "Phase 7 Report",
    "phase_8_collect_actions": "Phase 8 Action Collection",
    "phase_9_write_plan": "Phase 9 Plan",
    "phase_10_emit_and_wait": "Phase 10 Final Delivery",
}

SCREEN_SUMMARY_MAX_LINES = 6

QUADRANT_ORDER = ("q1_trc_nc", "q2_trc_nd", "q3_mrc_nc", "q4_mrc_nd")
QUADRANT_LABELS = {
    "q1_trc_nc": "TRC-NC",
    "q2_trc_nd": "TRC-ND",
    "q3_mrc_nc": "MRC-NC",
    "q4_mrc_nd": "MRC-ND",
}

IS_ISNT_DIMENSIONS = ("what", "where", "when", "extent")


class VisibilityReporter:
    """Emit user-visible progress and durable receipts.

    This is a runtime contract, not a documentation convention. When the graph
    invokes a phase, the phase start, phase end, and phase error surfaces must
    be written through this reporter. If a required sink fails, the run fails
    closed with VisibilityContractError.
    """

    def __init__(self, state: dict[str, Any], *, stream: TextIO | None = None) -> None:
        self.state = state
        self.stream = stream if stream is not None else sys.stderr
        run_dir_raw = state.get("run_dir")
        self.run_dir = Path(run_dir_raw) if run_dir_raw else None

    def phase_start(self, phase: str) -> dict[str, Any]:
        self._clear_stale_run_error()
        title = PHASE_TITLES.get(phase, phase)
        lines = [f"[Albert] {title}", "- Status: running"]
        if self.run_dir:
            lines.append(f"- Artifacts: {self.run_dir / 'stage-summaries.md'}")
        lines.append("- Next: brief summary will print when this phase completes.")
        screen = "\n".join(lines)
        self._write_screen(screen)
        receipt = self._progress_receipt(
            phase=phase,
            kind="phase_start",
            message="Phase started.",
            details=[
                f"Artifacts: {self.run_dir / 'stage-summaries.md'}"
                if self.run_dir else "Artifacts: unavailable until run_dir is set."
            ],
            screen=screen,
        )
        return {"visibility_receipt": receipt}

    def progress(self, phase: str, message: str, *details: str) -> dict[str, Any]:
        title = PHASE_TITLES.get(phase, phase)
        lines = [f"[Albert] {title}", f"- Progress: {message}"]
        lines.extend(f"- {detail}" for detail in details if detail)
        screen = "\n".join(lines)
        self._write_screen(screen)
        receipt = self._progress_receipt(
            phase=phase,
            kind="progress",
            message=message,
            details=[d for d in details if d],
            screen=screen,
        )
        return {"visibility_receipt": receipt}

    def phase_summary(self, phase: str) -> dict[str, Any]:
        lines = summarize_phase(phase, self.state)
        if not lines:
            lines = fallback_summary_lines(phase, self.state)
        if not lines:
            raise VisibilityContractError(
                f"No deterministic summary lines produced for {phase}",
                phase=phase,
                sink="summary",
            )

        title = PHASE_TITLES.get(phase, phase)
        screen_lines = [
            f"[Albert] {title}",
            *[f"- {line}" for line in lines[:SCREEN_SUMMARY_MAX_LINES]],
        ]
        markdown_lines = [f"### {title}", *[f"- {line}" for line in lines]]
        screen = "\n".join(screen_lines)
        markdown = "\n".join(markdown_lines)
        entry = {
            "ts": _isonow(),
            "kind": "phase_summary",
            "phase": phase,
            "title": title,
            "screen": screen,
            "markdown": markdown,
            "lines": lines,
        }

        self._write_screen(screen)
        patch: dict[str, Any] = {"screen_summary": markdown}
        if self.run_dir:
            self._ensure_run_dir()
            md_path = self.run_dir / "stage-summaries.md"
            jsonl_path = self.run_dir / "stage-summaries.jsonl"
            self._append_text(md_path, markdown + "\n\n")
            self._append_jsonl(jsonl_path, entry)
            patch["stage_summaries_path"] = str(md_path)
            entry["stage_summaries_path"] = str(md_path)

        # Return only the DELTA; AiEscapeMrcState.stage_summaries uses an
        # operator.add reducer, so concurrent (parallel-branch) appends merge
        # correctly instead of raising InvalidUpdateError.
        patch["stage_summaries"] = [entry]
        patch["visibility_receipt"] = entry
        return patch

    def phase_error(self, phase: str, exc: BaseException) -> dict[str, Any]:
        title = PHASE_TITLES.get(phase, phase)
        err = {
            "ts": _isonow(),
            "kind": "phase_error",
            "phase": phase,
            "title": title,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        if self.run_dir:
            err.update({
                "run_dir": str(self.run_dir),
                "progress_path": str(self.run_dir / "stage-progress.jsonl"),
                "stage_summaries_path": str(self.run_dir / "stage-summaries.md"),
            })
        screen = "\n".join(
            [
                f"[Albert] FAILED at {title}",
                f"- Error: {type(exc).__name__}: {_short(str(exc), 220)}",
                f"- Run directory: {self.run_dir}" if self.run_dir else "- Run directory: (missing)",
            ]
        )
        err["screen"] = screen
        self._write_screen(screen)
        if self.run_dir:
            self._ensure_run_dir()
            self._append_jsonl(self.run_dir / "stage-progress.jsonl", err)
            self._write_text(self.run_dir / "run-error.json", json.dumps(err, ensure_ascii=False, indent=2) + "\n")
        return {"visibility_receipt": err}

    def _progress_receipt(
        self,
        *,
        phase: str,
        kind: str,
        message: str,
        details: list[str],
        screen: str,
    ) -> dict[str, Any]:
        title = PHASE_TITLES.get(phase, phase)
        entry = {
            "ts": _isonow(),
            "kind": kind,
            "phase": phase,
            "title": title,
            "message": message,
            "details": details,
            "screen": screen,
        }
        if self.run_dir:
            self._ensure_run_dir()
            self._append_jsonl(self.run_dir / "stage-progress.jsonl", entry)
        return entry

    def _write_screen(self, text: str) -> None:
        try:
            self.stream.write(f"\n{text}\n\n")
            self.stream.flush()
        except Exception as exc:  # pragma: no cover - exercised with fake stream
            raise VisibilityContractError(
                f"Failed to write visibility output to screen: {exc}",
                sink="screen",
            ) from exc

    def _clear_stale_run_error(self) -> None:
        if self.run_dir is None:
            return
        error_path = self.run_dir / "run-error.json"
        if not error_path.exists():
            return
        try:
            error_path.unlink()
        except OSError as exc:
            raise VisibilityContractError(
                f"Failed to clear stale run error {error_path}: {exc}",
                sink=str(error_path),
            ) from exc

    def _ensure_run_dir(self) -> None:
        if self.run_dir is None:
            raise VisibilityContractError("run_dir is required for durable visibility receipts", sink="run_dir")
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise VisibilityContractError(
                f"Failed to create run visibility directory {self.run_dir}: {exc}",
                sink="run_dir",
            ) from exc

    def _append_jsonl(self, path: Path, entry: dict[str, Any]) -> None:
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise VisibilityContractError(
                f"Failed to append visibility receipt {path}: {exc}",
                sink=str(path),
            ) from exc

    def _append_text(self, path: Path, text: str) -> None:
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(text)
        except OSError as exc:
            raise VisibilityContractError(
                f"Failed to append visibility text {path}: {exc}",
                sink=str(path),
            ) from exc

    def _write_text(self, path: Path, text: str) -> None:
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise VisibilityContractError(
                f"Failed to write visibility text {path}: {exc}",
                sink=str(path),
            ) from exc


def emit_phase_start_summary(phase: str, state: dict[str, Any]) -> dict[str, Any]:
    """Print and persist a phase-start receipt."""
    return VisibilityReporter(state).phase_start(phase)


def emit_stage_progress(phase: str, state: dict[str, Any], message: str, *details: str) -> dict[str, Any]:
    """Print and persist an in-phase progress receipt."""
    return VisibilityReporter(state).progress(phase, message, *details)


def emit_stage_summary(phase: str, state: dict[str, Any]) -> dict[str, Any]:
    """Print and persist a compact Markdown summary for one completed phase."""
    return VisibilityReporter(state).phase_summary(phase)


def emit_phase_error(phase: str, state: dict[str, Any], exc: BaseException) -> dict[str, Any]:
    """Print and persist a deterministic failure receipt."""
    return VisibilityReporter(state).phase_error(phase, exc)


def write_run_error(run_dir: Path, phase: str, exc: BaseException) -> dict[str, Any]:
    """Write a run-error.json artifact for failures outside graph node wrappers."""
    return VisibilityReporter({"run_dir": str(run_dir)}).phase_error(phase, exc)


def summarize_phase(phase: str, state: dict[str, Any]) -> list[str]:
    if phase == "phase_0_research":
        return _research_summary_lines(state)
    if phase == "phase_1_is_isnt":
        return _is_isnt_summary_lines(state)
    if phase == "phase_2_why_analysis":
        return _why_summary_lines(state)
    if phase == "phase_3_rc_audit":
        return _audit_lines(state, 3)
    if phase == "phase_4_actions":
        return _action_summary_lines(state)
    if phase == "phase_5_prevention_audit":
        return _audit_lines(state, 5)
    if phase == "phase_6_verification":
        return _verification_summary_lines(state)
    if phase == "phase_7_report":
        report_path = state.get("report_path")
        size = _file_size(report_path)
        return [
            _closure_summary_line(state.get("closure_audit")),
            f"Report: {report_path or '(missing)'}{f' ({size} bytes)' if size is not None else ''}.",
        ]
    if phase == "phase_8_collect_actions":
        return _collected_actions_summary_lines(state)
    if phase == "phase_9_write_plan":
        plan_path = state.get("plan_path")
        size = _file_size(plan_path)
        return [
            _plan_summary_line(plan_path),
            f"Plan: {plan_path or '(missing)'}{f' ({size} bytes)' if size is not None else ''}.",
        ]
    if phase == "phase_10_emit_and_wait":
        return _delivery_summary_lines(state)
    return []


def _research_summary_lines(state: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for label, key in (
        ("Specific research signal", "websearch_specific"),
        ("Meta research signal", "websearch_meta"),
        ("Cross-domain signal", "websearch_cross_domain"),
    ):
        item = _first_mapping(state.get(key))
        if item is None:
            lines.append(_content_missing(key))
            continue
        subject = item.get("query") or item.get("path") or item.get("title") or key
        finding = item.get("results") or item.get("content") or item.get("summary") or item
        lines.append(f"{label}: {_short(subject, 80)} -> {_short(finding, 180)}")

    wiki = _first_mapping(state.get("wiki_pages"))
    memory = _first_mapping(state.get("memory_entries"))
    if wiki or memory:
        context = []
        if wiki:
            context.append(f"wiki {_short(wiki.get('path') or wiki.get('title') or wiki, 80)}")
        if memory:
            context.append(f"memory {_short(memory.get('path') or memory.get('title') or memory, 80)}")
        lines.append(f"Internal context: {'; '.join(context)}.")
    else:
        lines.append(_content_missing("wiki_pages or memory_entries"))
    return lines


def _is_isnt_summary_lines(state: dict[str, Any]) -> list[str]:
    table = state.get("is_isnt_table")
    if not isinstance(table, dict):
        return [_content_missing("is_isnt_table")]

    lines: list[str] = []
    for dim in IS_ISNT_DIMENSIONS:
        row = table.get(dim)
        if not isinstance(row, dict):
            lines.append(_content_missing(f"is_isnt_table.{dim}"))
            continue
        is_value = _field_text(row, ("is",))
        is_not = _field_text(row, ("is_not", "isnt", "not"))
        distinction = _field_text(row, ("distinction", "boundary", "difference"))
        if not (is_value or is_not or distinction):
            lines.append(_content_missing(f"is_isnt_table.{dim}"))
            continue
        lines.append(
            f"{dim}: IS {_short(is_value or '(missing)', 90)}; "
            f"IS NOT {_short(is_not or '(missing)', 90)}; "
            f"boundary {_short(distinction or '(missing)', 110)}."
        )
    return lines


def _why_summary_lines(state: dict[str, Any]) -> list[str]:
    chains = state.get("why_chains")
    if not isinstance(chains, dict):
        return [_content_missing("why_chains")]

    lines: list[str] = []
    for quadrant in QUADRANT_ORDER:
        label = QUADRANT_LABELS[quadrant]
        chain = chains.get(quadrant)
        if chain is None:
            lines.append(_content_missing(f"why_chains.{quadrant}"))
            continue
        root = _chain_tail(chain)
        if not root:
            lines.append(_content_missing(f"why_chains.{quadrant}.root"))
            continue
        lines.append(f"{label} root cause: {root}")
    return lines


def _action_summary_lines(state: dict[str, Any]) -> list[str]:
    corrective = state.get("corrective_actions") or {}
    prevention = state.get("prevention_actions") or {}
    lines = [
        _action_line("TRC-NC corrective", corrective.get("q1_trc_nc"), "corrective_actions.q1_trc_nc"),
        _action_line("TRC-ND corrective", corrective.get("q2_trc_nd"), "corrective_actions.q2_trc_nd"),
        _action_line("MRC-NC prevention", prevention.get("q3_mrc_nc"), "prevention_actions.q3_mrc_nc"),
        _action_line("MRC-ND prevention", prevention.get("q4_mrc_nd"), "prevention_actions.q4_mrc_nd"),
        f"Metadata: corrective actions {_count(corrective)}; prevention actions {_count(prevention)}.",
    ]
    return lines


def _action_line(label: str, action: Any, field: str) -> str:
    if not isinstance(action, dict):
        return f"{label}: {_content_missing(field)}"
    action_text = _field_text(action, ("action", "description", "title"))
    if not action_text:
        return f"{label}: {_content_missing(f'{field}.action')}"

    if label.endswith("prevention"):
        gate = action.get("gate_test")
        gate_text = _gate_test_text(gate)
        failure_mode = _field_text(action, ("failure_mode_of_prevention", "scope_justification"))
        detail = gate_text or failure_mode
        if detail:
            return f"{label}: {_short(action_text, 150)}; gate {detail}."
        return f"{label}: {_short(action_text, 190)}"

    rationale = _field_text(action, ("rationale", "evidence_of_completion", "owner"))
    if rationale:
        return f"{label}: {_short(action_text, 150)}; rationale {_short(rationale, 90)}."
    return f"{label}: {_short(action_text, 190)}"


def _verification_summary_lines(state: dict[str, Any]) -> list[str]:
    plan = state.get("verification_plan")
    proof = state.get("proof_of_action")
    rows = _verification_rows(plan, proof)
    if not rows:
        return [_content_missing("verification_plan.quadrants")]

    lines: list[str] = []
    for quadrant in QUADRANT_ORDER:
        label = QUADRANT_LABELS[quadrant]
        row = rows.get(quadrant)
        if not isinstance(row, dict):
            lines.append(_content_missing(f"verification_plan.{quadrant}"))
            continue
        metric = _field_text(row, ("metric",))
        target = _field_text(row, ("target",))
        data_source = _field_text(row, ("data_source", "source", "data"))
        if not (metric or target or data_source):
            lines.append(_content_missing(f"verification_plan.{quadrant}.metric_target_data_source"))
            continue
        lines.append(
            f"{label} verification: metric {_short(metric or '(missing)', 80)}; "
            f"target {_short(target or '(missing)', 80)}; "
            f"data source {_short(data_source or _content_missing(f'verification_plan.{quadrant}.data_source'), 90)}."
        )

    if isinstance(plan, dict) and plan.get("overall_timeframe"):
        lines.append(f"Timeframe: {_short(plan.get('overall_timeframe'), 120)}.")
    return lines


def _verification_rows(plan: Any, proof: Any) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if isinstance(plan, dict):
        quadrants = plan.get("quadrants")
        if isinstance(quadrants, list):
            for row in quadrants:
                if isinstance(row, dict) and row.get("quadrant"):
                    rows[str(row["quadrant"])] = row
    if rows:
        return rows
    if isinstance(proof, dict):
        return {str(k): v for k, v in proof.items() if isinstance(v, dict)}
    return rows


def _closure_summary_line(closure: Any) -> str:
    if not isinstance(closure, dict) or not closure:
        return _content_missing("closure_audit")
    failed = [str(k) for k, v in closure.items() if v is False]
    if failed:
        return f"Closure outcome: blocked by {', '.join(failed[:4])}."
    true_keys = [str(k) for k, v in closure.items() if v is True]
    if true_keys:
        return f"Closure outcome: passed gates {_join(true_keys, limit=5)}."
    return f"Closure outcome: {_short(closure)}"


def _collected_actions_summary_lines(state: dict[str, Any]) -> list[str]:
    actions_path = state.get("actions_path")
    actions = _read_json(actions_path)
    preview = _actions_preview(actions)
    if not preview:
        preview = _content_missing("actions_path.actions")
    return [
        f"Dispatch content: {preview}",
        f"Actions file: {actions_path or '(missing)'}.",
        f"Actions collected: {state.get('actions_count', 0)}.",
    ]


def _plan_summary_line(plan_path: Any) -> str:
    text = _read_text(plan_path)
    if not text:
        return _content_missing("plan_path")
    tasks = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Task"):
            tasks.append(stripped.lstrip("# ").strip())
        if len(tasks) >= 3:
            break
    if tasks:
        return f"Plan tasks: {_join(tasks, limit=3)}."
    first_heading = next((line.strip("# ").strip() for line in text.splitlines() if line.startswith("#")), "")
    return f"Plan content: {_short(first_heading or text, 180)}"


def _delivery_summary_lines(state: dict[str, Any]) -> list[str]:
    recipient_to = state.get("recipient_to")
    recipient_cc = state.get("recipient_cc")
    recipient_source = state.get("recipient_source")
    result = state.get("email_delivery_result") or "(missing)"
    error = state.get("email_delivery_error")
    return [
        f"Delivery outcome: email {result} for run {state.get('run_id') or '(missing run_id)'}.",
        f"Recipient: To={recipient_to or '(missing)'}; Cc={recipient_cc or '(none)'}; source={recipient_source or '(missing)'}.",
        f"Report: {state.get('report_path') or '(missing)'}.",
        f"Plan: {state.get('plan_path') or '(missing)'}.",
        f"Stage summaries: {state.get('stage_summaries_path') or '(missing)'}.",
        f"Delivery status: {state.get('delivery_status_path') or '(missing)'}{f'; error: {_short(error, 140)}' if error else ''}.",
    ]


def fallback_summary_lines(phase: str, state: dict[str, Any]) -> list[str]:
    """Return deterministic fallback lines when a phase-specific summary is empty."""
    status_key = _phase_complete_key(phase)
    status = "complete" if status_key and state.get(status_key) else "completed with no phase-specific marker"
    keys = _join(sorted(str(k) for k in state.keys()), limit=8)
    return [
        f"Status: {status}.",
        f"State keys observed: {keys}.",
    ]


def _phase_complete_key(phase: str) -> str | None:
    parts = phase.split("_")
    if len(parts) >= 2 and parts[0] == "phase" and parts[1].isdigit():
        return f"phase_{parts[1]}_complete"
    return None


def _audit_lines(state: dict[str, Any], phase_num: int) -> list[str]:
    rounds = state.get(f"phase_{phase_num}_rounds")
    residual = state.get(f"phase_{phase_num}_residual_risks")
    lines = [
        f"Status: {state.get(f'phase_{phase_num}_status') or '(missing)'}; "
        f"verdict: {state.get(f'phase_{phase_num}_verdict') or '(missing)'}.",
    ]
    challenge = _audit_key_challenge(rounds)
    if challenge:
        lines.append(f"Key challenge: {challenge}")
    elif isinstance(rounds, list) and rounds:
        lines.append("Key challenge: no addressable or residual weakness recorded.")
    else:
        lines.append(_content_missing(f"phase_{phase_num}_rounds.weaknesses.issue"))

    residual_line = _residual_risk_summary(residual)
    if residual_line:
        lines.append(f"Residual risk: {residual_line}")
    elif isinstance(residual, list):
        lines.append("Residual risk: none recorded after audit exhaustion.")
    else:
        lines.append(_content_missing(f"phase_{phase_num}_residual_risks"))

    lines.append(f"Metadata: audit rounds {_count(rounds)}; residual risks {_count(residual)}.")
    return lines


def _audit_key_challenge(rounds: Any) -> str:
    if not isinstance(rounds, list) or not rounds:
        return ""
    for audit in reversed(rounds):
        if not isinstance(audit, dict):
            continue
        for key in ("key_challenge", "key_conclusion", "final_conclusion", "why", "critique", "summary"):
            if audit.get(key):
                return _short(audit[key])
        weaknesses = audit.get("weaknesses")
        if isinstance(weaknesses, list) and weaknesses:
            for weakness in weaknesses:
                text = _weakness_text(weakness)
                if text:
                    return text
    return ""


def _residual_risk_summary(residual: Any) -> str:
    if not isinstance(residual, list) or not residual:
        return ""
    for risk in residual:
        text = _weakness_text(risk)
        if text:
            return text
    return _short(residual[0])


def _weakness_text(weakness: Any) -> str:
    if not isinstance(weakness, dict):
        return _short(weakness)
    parts = []
    quadrant = weakness.get("quadrant")
    classification = weakness.get("classification")
    if quadrant or classification:
        parts.append(f"{QUADRANT_LABELS.get(str(quadrant), str(quadrant or 'unknown'))} {classification or 'issue'}")
    issue = _field_text(weakness, ("issue", "summary", "risk"))
    if issue:
        parts.append(_short(issue, 120))
    fix = _field_text(weakness, ("suggested_fix", "mitigation", "evidence"))
    if fix:
        parts.append(f"fix/evidence {_short(fix, 90)}")
    return "; ".join(parts)


def _chain_tail(chain: Any) -> str:
    if isinstance(chain, dict):
        for key in ("root", "root_cause", "final_cause", "conclusion", "summary"):
            if chain.get(key):
                return _short(chain[key])
        whys = chain.get("whys")
        if isinstance(whys, list) and whys:
            last = whys[-1]
            if isinstance(last, dict):
                return _short(last.get("why") or last.get("new_insight") or last)
            return _short(last)
    return _short(chain)


def _content_missing(field: str) -> str:
    return f"content missing: {field}"


def _first_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return None


def _field_text(value: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(value, dict):
        return ""
    for key in keys:
        candidate = value.get(key)
        if candidate is None:
            continue
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, (int, float, bool)):
            return str(candidate)
        if isinstance(candidate, (dict, list)) and candidate:
            return _short(candidate)
    return ""


def _gate_test_text(gate: Any) -> str:
    if not isinstance(gate, dict):
        return ""
    parts = []
    for key in ("scope", "persistence", "measurability"):
        if gate.get(key):
            evidence = gate.get(f"{key}_evidence")
            value = str(gate[key])
            if evidence:
                value += f" ({_short(evidence, 60)})"
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def _read_json(path: Any) -> Any:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Any) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _actions_preview(actions: Any) -> str:
    if not isinstance(actions, list) or not actions:
        return ""
    titles = []
    for action in actions:
        if not isinstance(action, dict):
            titles.append(_short(action, 80))
        else:
            title = _field_text(action, ("title", "description", "action"))
            if title:
                source = action.get("source_quadrant")
                titles.append(f"{source}: {_short(title, 70)}" if source else _short(title, 80))
        if len(titles) >= 3:
            break
    return _join(titles, limit=3)


def _count(value: Any) -> int:
    if isinstance(value, (list, tuple, dict, set)):
        return len(value)
    return 0 if value is None else 1


def _join(value: Any, limit: int = 6) -> str:
    items = list(value or [])
    if not items:
        return "(none)"
    shown = ", ".join(str(x) for x in items[:limit])
    if len(items) > limit:
        shown += f", +{len(items) - limit} more"
    return shown


def _short(value: Any, limit: int = 180) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _file_size(path: Any) -> int | None:
    if not path:
        return None
    try:
        return Path(path).stat().st_size
    except OSError:
        return None


def _isonow() -> str:
    return datetime.now(timezone.utc).isoformat()
