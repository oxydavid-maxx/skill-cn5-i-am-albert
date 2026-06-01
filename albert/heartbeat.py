"""Heartbeat thread for long-running Albert runs.

Emits human-readable progress summaries to stderr every HEARTBEAT_INTERVAL seconds
(default 300s = 5 min). Also posts to Telegram diagnostics topic if configured.

Design motivation: progress.jsonl captures every LLM call + phase transition, but
per-event logs are noisy. User cannot tell from 100+ lines of JSON whether the run
is making progress or stuck. The heartbeat aggregates recent events into a single
line a human can read, and flags stalls where no new event arrived.

Started automatically by run_albert.py at launch. Runs as a daemon thread so it exits
with the main process when the LangGraph pipeline completes.

Persisted-requirement source: `~/.claude/feedback_skill_progress_reporting.md`
(long-running skills >10 min MUST emit human-readable progress every 5-10 min).

# WIKI-CONSULTED: silent-staleness#data-level-freshness-check
# WIKI-CONSULTED: silent-staleness#misleading-metadata-trap
# WIKI-CONSULTED: wiki-to-code-traceability#triple-marker-convention
# WIKI-CONSULTED: long-running-progress-heartbeat#built-in-not-external
# WIKI-CONSULTED: instruction-failure-escalation-ladder#text-instructions-decay
# WIKI-FINDING: silent-staleness says freshness must be derived from content, not wall
#   clock. Applied here: stall detection compares time.time() against the ts field
#   INSIDE the last progress.jsonl event (content timestamp), not against the heartbeat
#   thread's own clock. If the main process hangs and writes no events, time.time()
#   advances but event.ts does not, so the gap grows and triggers a stall warning.
# WIKI-FINDING: progress.py docstring claimed 'An external monitor can tail this file
#   to report every 10 min' - promise made, monitor never built, user was blind to
#   long-run progress. Text-only directive rot per Instruction Failure Escalation Ladder.
# WIKI-FINDING: long-running-progress-heartbeat says heartbeat must answer "what's
#   happening + how long left + what's next", not just "still alive". Phase-name +
#   typical-duration + next-phase fields convert a heartbeat from liveness ping into
#   actionable progress signal. Generic STALL_THRESHOLD_SEC=600 was the failure mode
#   for Phase 7 (~750s typical) ??false-positive stall warnings during normal LLM call.
# WIKI-ACTION: built-in (daemon thread inside run_albert.py), not external - removes the
#   'someone will build the monitor separately' failure mode. Heartbeat starts at
#   process init and dies with the process, so it cannot be forgotten.
# WIKI-ACTION: emit destination is stderr + optional Telegram diagnostics topic -
#   reaches user both at terminal and on phone, no single point of delivery failure.
# WIKI-ACTION: per-phase stall threshold (TYPICAL_PHASE_DURATIONS_SEC[phase] * 1.5)
#   replaces the static 600s. Phase 7 stall threshold = 1125s, Phase 1 = 90s ??both
#   correctly calibrated to actual phase work.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

DEFAULT_INTERVAL_SEC = 300   # 5 min

# Human-readable phase descriptions. Keys must match the phase names emitted
# by graph.py via _wrap_with_progress(). Values follow the convention
# "Phase N/10 (short description, optional detail)".
PHASE_NAMES: dict[str, str] = {
    "phase_0_research": "Phase 0/10 (research, 8 parallel WebSearches)",
    "phase_1_is_isnt": "Phase 1/10 (IS/IS NOT extraction)",
    "phase_2_why_analysis": "Phase 2/10 (Why analysis, 4 parallel quadrants)",
    "phase_3_rc_audit": "Phase 3/10 (RC audit, 3 rounds)",
    "phase_4_actions": "Phase 4/10 (corrective + prevention actions)",
    "phase_5_prevention_audit": "Phase 5/10 (prevention audit, 3 rounds)",
    "phase_6_verification": "Phase 6/10 (verification plan)",
    "phase_7_report": "Phase 7/10 (report render, single ~13min LLM call)",
    "phase_8_collect_actions": "Phase 8/10 (action collection, instant)",
    "phase_9_write_plan": "Phase 9/10 (plan generation via direct call_claude)",
    "phase_10_emit_and_wait": "Phase 10/10 (final report/plan delivery)",
}

# Calibrated typical phase durations, derived from observed runs (2026-04-25/26).
# Used for two purposes:
#   (a) inform the user of expected wait time for the current phase
#   (b) compute a phase-specific stall threshold (typical * 1.5)
TYPICAL_PHASE_DURATIONS_SEC: dict[str, int] = {
    "phase_0_research": 250,
    "phase_1_is_isnt": 60,
    "phase_2_why_analysis": 380,
    "phase_3_rc_audit": 600,
    "phase_4_actions": 130,
    "phase_5_prevention_audit": 700,
    "phase_6_verification": 110,
    "phase_7_report": 750,
    "phase_8_collect_actions": 1,
    "phase_9_write_plan": 110,
    "phase_10_emit_and_wait": 5,
}

# Successor phase per graph.py edge list. Used to show "next: ..." in heartbeat.
NEXT_PHASE: dict[str, str] = {
    "phase_0_research": "phase_1_is_isnt",
    "phase_1_is_isnt": "phase_2_why_analysis",
    "phase_2_why_analysis": "phase_3_rc_audit",
    "phase_3_rc_audit": "phase_4_actions",
    "phase_4_actions": "phase_5_prevention_audit",
    "phase_5_prevention_audit": "phase_6_verification",
    "phase_6_verification": "phase_7_report",
    "phase_7_report": "phase_8_collect_actions",
    "phase_8_collect_actions": "phase_9_write_plan",
    "phase_9_write_plan": "phase_10_emit_and_wait",
    "phase_10_emit_and_wait": "END",
}

# Fallback stall threshold used when a phase has no calibrated typical duration
# (e.g., a new phase added without updating TYPICAL_PHASE_DURATIONS_SEC). Keep
# comfortably above the largest current typical (750s) so unknowns don't false-alarm.
DEFAULT_STALL_THRESHOLD_SEC = 1200


def _stall_threshold_for(phase: str) -> int:
    """Phase-specific stall threshold = typical * 1.5, with sensible floor + fallback.

    Floor of 60s prevents instant-phase false alarms (phase_8 typical=1s would
    otherwise yield 1.5s threshold and trigger STALL on any tiny pause).
    """
    typical = TYPICAL_PHASE_DURATIONS_SEC.get(phase)
    if typical is None:
        return DEFAULT_STALL_THRESHOLD_SEC
    threshold = int(typical * 1.5)
    return max(threshold, 60)


def _format_minutes(seconds: float) -> str:
    """Compact human form: 750s -> '~13min', 45s -> '45s'."""
    if seconds < 60:
        return f"{int(seconds)}s"
    return f"~{int(round(seconds / 60))}min"


def _load_telegram_cfg() -> dict | None:
    cfg_path = Path.home() / ".claude" / "telegram.json"
    if not cfg_path.exists():
        return None
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _post_telegram(msg: str, cfg: dict) -> None:
    try:
        import requests

        token = cfg["bot_token"]
        chat = cfg["group_chat_id"]
        thread = cfg.get("topics", {}).get("diagnostics")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat, "text": msg}
        if thread is not None:
            data["message_thread_id"] = thread
        requests.post(url, data=data, timeout=10)
    except Exception:
        pass  # heartbeat never raises up to the LangGraph thread


def _read_progress_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return events


def _format_heartbeat_line(run_id: str, events: list[dict], now: float | None = None) -> tuple[str, bool, str]:
    """Build the single-line heartbeat message + stall flag + current phase.

    Pure function, called by the loop and the tests. Returns:
      (message, is_stalled, current_phase)
    """
    if now is None:
        now = time.time()
    if not events:
        return (f"[heartbeat] {run_id} | waiting for first event", False, "")

    last = events[-1]
    phase = last.get("phase", "?")
    event = last.get("event", "?")
    total = last.get("total_elapsed_sec", 0)
    minutes = total / 60.0
    last_ts = last.get("ts", now)
    since_last = now - last_ts

    threshold = _stall_threshold_for(phase)
    stalled = since_last > threshold

    phase_label = PHASE_NAMES.get(phase, phase)
    typical = TYPICAL_PHASE_DURATIONS_SEC.get(phase)
    next_phase_key = NEXT_PHASE.get(phase, "?")
    next_phase_label = PHASE_NAMES.get(next_phase_key, next_phase_key)

    if typical is not None and typical > 0:
        progress_bit = (
            f"event {event} in flight {int(since_last)}s/typical {typical}s "
            f"({_format_minutes(typical)})"
        )
    else:
        progress_bit = f"event {event} in flight {int(since_last)}s"

    msg = (
        f"[heartbeat] {run_id} | {phase_label} | {minutes:.1f}min total | "
        f"{progress_bit} | next: {next_phase_label}"
    )
    return (msg, stalled, phase)


def _heartbeat_loop(run_dir: Path, run_id: str, interval_sec: int, to_telegram: bool) -> None:
    progress_path = run_dir / "progress.jsonl"
    last_event_count = 0
    tg_cfg = _load_telegram_cfg() if to_telegram else None
    sys.stderr.write(
        f"[heartbeat] started: run_id={run_id} interval={interval_sec}s "
        f"telegram={'on' if tg_cfg else 'off'}\n"
    )
    sys.stderr.flush()

    while True:
        time.sleep(interval_sec)
        try:
            events = _read_progress_events(progress_path)
            n = len(events)
            new_events = n - last_event_count
            last_event_count = n

            if n == 0:
                sys.stderr.write(f"[heartbeat] run_id={run_id} - waiting for first event\n")
                sys.stderr.flush()
                continue

            msg, stalled, phase = _format_heartbeat_line(run_id, events)
            # Append per-interval delta as suffix (not in core line so tests stay deterministic)
            full_msg = f"{msg} | new_events_in_last_{interval_sec // 60}min={new_events}"
            sys.stderr.write(full_msg + "\n")
            sys.stderr.flush()
            if tg_cfg is not None:
                _post_telegram(full_msg, tg_cfg)

            if stalled:
                threshold = _stall_threshold_for(phase)
                last = events[-1]
                last_ts = last.get("ts", time.time())
                since_last = time.time() - last_ts
                warn = (
                    f"[heartbeat STALL WARNING] run_id={run_id}: no new progress event "
                    f"for {since_last:.0f}s (phase-specific threshold {threshold}s for "
                    f"{phase}). Last was {last.get('event','?')} in {phase}."
                )
                sys.stderr.write(warn + "\n")
                sys.stderr.flush()
                if tg_cfg is not None:
                    _post_telegram(warn, tg_cfg)

        except Exception as e:
            # Never raise - heartbeat failures must not kill the run
            sys.stderr.write(f"[heartbeat] internal error: {e}\n")
            sys.stderr.flush()


def start(run_dir: Path, run_id: str,
          interval_sec: int | None = None,
          to_telegram: bool = True) -> threading.Thread:
    """Start a daemon heartbeat thread. Returns the thread (for tests).

    Environment overrides:
      HEARTBEAT_INTERVAL_SEC  - override default 300s
      HEARTBEAT_DISABLE=1     - skip starting the heartbeat (for smoke tests)
    """
    if os.environ.get("HEARTBEAT_DISABLE") == "1":
        sys.stderr.write("[heartbeat] disabled via HEARTBEAT_DISABLE=1\n")
        sys.stderr.flush()
        return threading.Thread(target=lambda: None, daemon=True)

    if interval_sec is None:
        try:
            interval_sec = int(os.environ.get("HEARTBEAT_INTERVAL_SEC", DEFAULT_INTERVAL_SEC))
        except ValueError:
            interval_sec = DEFAULT_INTERVAL_SEC

    t = threading.Thread(
        target=_heartbeat_loop,
        args=(run_dir, run_id, interval_sec, to_telegram),
        daemon=True,
        name=f"ai-escape-mrc-heartbeat-{run_id}",
    )
    t.start()
    return t
