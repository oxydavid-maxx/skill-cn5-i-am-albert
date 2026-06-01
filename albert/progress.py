"""Per-event progress logging for Albert runs.

Writes one JSONL record to runs/<run_id>/progress.jsonl for every LLM call and
phase transition. Each event:
{
  "ts": float,
  "phase": "phase_0_research" | ...,
  "event": "phase_start" | "llm_call_start" | "llm_call_end" | "phase_end" | "stall_warning",
  "detail": "...",
  "model": "environment-default" | explicit model override | None,
  "elapsed_sec": float,
  "total_elapsed_sec": float
}

Also tees each event to stderr for live tailing.

**Aggregated human-readable progress** is emitted separately by `albert.heartbeat`,
which starts a daemon thread at run_albert.py launch and prints a single-line summary
every 5 min (plus stall warnings at 10 min without a new event). This module only
records the raw events; heartbeat aggregates them.

Historical note: prior docstring promised 'an external monitor can tail this file'
??that monitor was never built, leaving users blind to long-run progress for
multiple weeks. Replaced 2026-04-25 with the built-in heartbeat thread per
~/.claude/feedback_skill_progress_reporting.md.
"""
import json
import os
import time
from pathlib import Path
from typing import Optional

from albert.errors import VisibilityContractError


_run_start_ts: Optional[float] = None
_phase_start_ts: Optional[float] = None
_last_event_ts: Optional[float] = None
_current_phase: Optional[str] = None
_progress_path: Optional[Path] = None


def init(run_dir: Path):
    global _run_start_ts, _progress_path, _last_event_ts
    _progress_path = Path(run_dir) / "progress.jsonl"
    try:
        _progress_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VisibilityContractError(
            f"Failed to create progress directory {_progress_path.parent}: {exc}",
            sink=str(_progress_path.parent),
        ) from exc
    _run_start_ts = time.time()
    _last_event_ts = _run_start_ts
    emit("init", "init", {"run_dir": str(run_dir)})


def emit(phase: str, event: str, detail: dict | None = None, model: str | None = None):
    global _last_event_ts, _current_phase
    now = time.time()
    if event == "phase_start":
        global _phase_start_ts
        _phase_start_ts = now
        _current_phase = phase
    rec = {
        "ts": now,
        "phase": phase,
        "event": event,
        "model": model,
        "elapsed_sec": round(now - (_phase_start_ts or now), 2) if _phase_start_ts else 0,
        "total_elapsed_sec": round(now - (_run_start_ts or now), 2) if _run_start_ts else 0,
        "detail": detail or {},
    }
    _last_event_ts = now
    if _progress_path:
        try:
            with open(_progress_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise VisibilityContractError(
                f"Failed to append progress event {_progress_path}: {exc}",
                phase=phase,
                sink=str(_progress_path),
            ) from exc
    try:
        import sys
        sys.stderr.write(f"[progress] {phase} {event} +{rec['elapsed_sec']}s (total {rec['total_elapsed_sec']}s) {detail or ''}\n")
        sys.stderr.flush()
    except Exception as exc:
        raise VisibilityContractError(
            f"Failed to write progress event to screen: {exc}",
            phase=phase,
            sink="screen",
        ) from exc


def phase_start(phase: str, detail: dict | None = None):
    emit(phase, "phase_start", detail)


def phase_end(phase: str, detail: dict | None = None):
    emit(phase, "phase_end", detail)


def llm_call_start(phase: str, purpose: str, model: str | None = None):
    emit(phase, "llm_call_start", {"purpose": purpose}, model=model)


def llm_call_end(phase: str, purpose: str, model: str | None = None, tokens: int | None = None, error: str | None = None):
    detail = {"purpose": purpose}
    if tokens is not None:
        detail["tokens"] = tokens
    if error:
        detail["error"] = error
    emit(phase, "llm_call_end" if not error else "llm_call_error", detail, model=model)


def stall_check(threshold_sec: float = 600):
    """Return True if more than threshold_sec elapsed since last event."""
    if _last_event_ts is None:
        return False
    return (time.time() - _last_event_ts) > threshold_sec
