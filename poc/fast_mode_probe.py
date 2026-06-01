"""Fast-mode reachability probe (gate for the latency-speedup work).

Issues ONE real `call_claude` per wiring variant against the installed
claude-agent-sdk 0.1.63 / claude CLI, plus a control with no fast-mode wiring.
Prints elapsed seconds + output length for each so we can see (a) whether any
fast-mode wiring engages WITHOUT erroring on this CLI/subscription, and (b) the
measured speedup vs the control.

Fast mode (per the task) = API speed="fast" + beta header fast-mode-2026-02-01.
On the SDK→CLI transport that maps to:
  betas=["fast-mode-2026-02-01"]   -> CLI flag  --betas fast-mode-2026-02-01
  extra_args={"speed":"fast"}      -> CLI flag  --speed fast
We try several plausible passthroughs and record which one runs clean.

Run:  py -3 poc/fast_mode_probe.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Make the repo importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from albert.no_console import patch_anyio_open_process_for_windows

patch_anyio_open_process_for_windows()

from claude_agent_sdk import ClaudeAgentOptions, query

_SDK_ENV = {
    "CLAUDECODE": "",
    "CLAUDE_SDK_CALL": "1",
    "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK": "1",
}

BETA = "fast-mode-2026-02-01"

# A prompt that reliably produces ~2-3K chars of output.
PROMPT = (
    "Write a concise but complete explanation (about 2000-3000 characters) of "
    "how a CAN bus arbitration mechanism resolves contention between two ECUs "
    "transmitting simultaneously. Cover: dominant vs recessive bits, bitwise "
    "arbitration, identifier priority, and why the loser backs off without "
    "corrupting the winner's frame. Plain prose, no code."
)
SYSTEM = "You are a precise automotive-systems explainer."


async def _collect(msg_iter) -> str:
    parts: list[str] = []
    async for msg in msg_iter:
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                t = getattr(block, "text", None)
                if t:
                    parts.append(t)
    return "\n".join(parts)


def _run_variant(label: str, *, betas=None, extra_args=None, settings=None) -> dict:
    """Run one query with the given fast-mode wiring. Returns a result dict."""
    kwargs = dict(
        system_prompt=SYSTEM,
        setting_sources=None,
        allowed_tools=[],
        max_turns=3,
        env=dict(_SDK_ENV),
    )
    if betas is not None:
        kwargs["betas"] = betas
    if extra_args is not None:
        kwargs["extra_args"] = extra_args
    if settings is not None:
        kwargs["settings"] = settings

    t0 = time.time()
    try:
        options = ClaudeAgentOptions(**kwargs)

        async def _go():
            return await _collect(query(prompt=PROMPT, options=options))

        text = asyncio.run(asyncio.wait_for(_go(), timeout=300))
        dt = time.time() - t0
        return {"label": label, "ok": True, "elapsed": dt, "chars": len(text),
                "error": None}
    except Exception as e:  # noqa: BLE001 — probe wants to record any failure
        dt = time.time() - t0
        return {"label": label, "ok": False, "elapsed": dt, "chars": 0,
                "error": f"{type(e).__name__}: {str(e)[:300]}"}


def main() -> None:
    variants = [
        ("control (no fast-mode wiring)", dict()),
        ("betas + extra_args speed=fast",
         dict(betas=[BETA], extra_args={"speed": "fast"})),
        ("betas + extra_args --speed=fast",
         dict(betas=[BETA], extra_args={"--speed": "fast"})),
        ("betas only", dict(betas=[BETA])),
        ("extra_args speed=fast only", dict(extra_args={"speed": "fast"})),
        ("settings {'speed':'fast'} + betas",
         dict(betas=[BETA], settings='{"speed": "fast"}')),
    ]

    results = []
    for label, wiring in variants:
        print(f"\n=== {label} ===", flush=True)
        r = _run_variant(label, **wiring)
        results.append(r)
        if r["ok"]:
            print(f"  OK   elapsed={r['elapsed']:.1f}s  chars={r['chars']}", flush=True)
        else:
            print(f"  FAIL elapsed={r['elapsed']:.1f}s  error={r['error']}", flush=True)

    print("\n========== SUMMARY ==========")
    control = next((r for r in results if r["label"].startswith("control")), None)
    for r in results:
        status = "OK  " if r["ok"] else "FAIL"
        speedup = ""
        if r["ok"] and control and control["ok"] and r is not control and r["elapsed"] > 0:
            speedup = f"  speedup_vs_control={control['elapsed'] / r['elapsed']:.2f}x"
        print(f"  [{status}] {r['label']:42s} {r['elapsed']:6.1f}s {r['chars']:6d} chars{speedup}")
        if not r["ok"]:
            print(f"           -> {r['error']}")

    engaged = [r for r in results if r["ok"] and not r["label"].startswith("control")]
    print("\nFast-mode reachable:", "YES" if engaged else "NO (no fast-mode variant ran clean)")
    if engaged:
        print("Working wiring variants (ran without error):")
        for r in engaged:
            print(f"  - {r['label']}  ({r['elapsed']:.1f}s)")


if __name__ == "__main__":
    main()
