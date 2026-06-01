"""Windows no-console helpers for Albert background execution."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = 0x08000000
_PATCHED = False


def hidden_creationflags(existing: int = 0) -> int:
    """Return subprocess creation flags that suppress console windows on Windows."""
    if os.name != "nt":
        return existing
    return existing | CREATE_NO_WINDOW


def pythonw_for_current_interpreter() -> str:
    """Prefer pythonw.exe over py.exe/python.exe for detached Windows helpers."""
    exe = Path(sys.executable)
    if os.name == "nt":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(exe)


def hidden_python_command(script: str | Path, *args: str) -> list[str]:
    """Build a command that starts Python without a visible console on Windows."""
    return [pythonw_for_current_interpreter(), str(script), *args]


def patch_anyio_open_process_for_windows() -> bool:
    """Patch anyio.open_process so SDK-spawned CLI children do not open a console.

    The Claude Agent SDK ultimately calls anyio.open_process(). Passing
    CREATE_NO_WINDOW at that seam keeps the behavior repo-owned, instead of
    relying on a patched copy of site-packages on one machine.
    """
    global _PATCHED
    if _PATCHED or os.name != "nt":
        return _PATCHED

    import anyio

    original = anyio.open_process
    if getattr(original, "_ai_escape_no_console", False):
        _PATCHED = True
        return True

    async def open_process_no_console(*args: Any, **kwargs: Any):
        kwargs["creationflags"] = hidden_creationflags(int(kwargs.get("creationflags", 0) or 0))
        return await original(*args, **kwargs)

    open_process_no_console._ai_escape_no_console = True  # type: ignore[attr-defined]
    open_process_no_console._ai_escape_original = original  # type: ignore[attr-defined]
    anyio.open_process = open_process_no_console
    _PATCHED = True
    return True
