# WIKI-EXEMPT: new typed-exception definitions ??no wiki-governed pattern applies
"""Typed exceptions for the Albert pipeline.

Typed exceptions make failure routing explicit and testable.
Each exception carries enough context for the FSM to emit a fail-closed
gate artifact (no degraded-success warnings per R13).
"""
from __future__ import annotations


class VisibilityContractError(Exception):
    """Runtime visibility receipt emission failed.

    Albert treats user-visible progress and durable phase receipts as
    deterministic runtime output, not as optional logging. This exception is
    raised when a required screen, progress, summary, or error artifact cannot
    be emitted.
    """

    def __init__(self, message: str, *, phase: str = "", sink: str = "") -> None:
        super().__init__(message)
        self.phase = phase
        self.sink = sink


class DegradedEmissionError(Exception):
    """A degraded run (status=='failed') tried to emit a non-refusal verdict/green light."""
    def __init__(self, message: str, predicate: str = "") -> None:
        super().__init__(message)
        self.predicate = predicate
