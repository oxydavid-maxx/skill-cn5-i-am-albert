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
